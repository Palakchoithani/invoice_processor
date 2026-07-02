import os
import queue
import shutil
import json
import threading
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config.db_config import PENDING_DIR, PROCESSING_DIR, FAILED_DIR, SUPPORTED_FORMATS
from services.processor import process_single_invoice
from services.database import (
    init_db, get_all_invoices, get_invoice_by_id,
    search_invoices, get_stats, get_job_by_hash, create_or_update_job, get_db
)
from models.invoice_model import DocumentJob
from services.file_handler import ensure_dirs, calculate_file_hash, move_to_failed
from services.duplicate_detector import run_duplicate_checks
from services.logger import log_info, log_error

app = FastAPI(title="InvoiceFlow", version="1.0.0")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

class FirestoreStreamer:
    def __init__(self):
        self._lock = threading.Lock()
        self._queues = set()
        self.invoices_watch = None
        self.jobs_watch = None

    @property
    def queues(self):
        return self._queues

    def add_queue(self, q):
        with self._lock:
            self._queues.add(q)

    def discard_queue(self, q):
        with self._lock:
            self._queues.discard(q)

    def start(self):
        db = get_db()
        if not self.invoices_watch:
            log_info("FirestoreStreamer: Attaching real-time listener on 'invoices' collection...")
            self.invoices_watch = db.collection("invoices").on_snapshot(self._on_invoices_change)
        if not self.jobs_watch:
            log_info("FirestoreStreamer: Attaching real-time listener on 'document_jobs' collection...")
            self.jobs_watch = db.collection("document_jobs").on_snapshot(self._on_jobs_change)

    def _on_invoices_change(self, col_snapshot, changes, read_time):
        invoices = []
        for doc in col_snapshot:
            data = doc.to_dict()
            data["id"] = doc.id
            invoices.append(data)
            
        invoices.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        log_info(f"FirestoreStreamer: Broadcast invoices update (count={len(invoices)})")
        self.broadcast("invoices", invoices)
        self.broadcast_stats()

    def _on_jobs_change(self, col_snapshot, changes, read_time):
        jobs = []
        for doc in col_snapshot:
            jobs.append(doc.to_dict())
            
        jobs.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        jobs = jobs[:500]
        
        log_info(f"FirestoreStreamer: Broadcast jobs update (count={len(jobs)})")
        self.broadcast("jobs", jobs)
        self.broadcast_stats()

    def broadcast_stats(self):
        from services.database import get_stats
        try:
            stats = get_stats()
            log_info("FirestoreStreamer: Broadcast stats update")
            self.broadcast("stats", stats)
        except Exception as e:
            log_error(f"FirestoreStreamer: Error broadcasting stats: {e}")

    def broadcast(self, event_type: str, data: any):
        msg = json.dumps({"type": event_type, "data": data})
        with self._lock:
            snapshot = list(self._queues)
        for q in snapshot:
            try:
                q.put_nowait(msg)
            except Exception:
                pass

streamer = FirestoreStreamer()

# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    ensure_dirs()
    try:
        init_db()
        log_info("App started. DB ready.")
        streamer.start()
        # Startup Sync: Repair broken states
        # Any file left in processing/ was interrupted. Move to failed.
        for f in Path(PROCESSING_DIR).iterdir():
            if not f.is_file():
                continue
            try:
                log_info(f"Startup Sync: Found interrupted file {f.name}. Moving to failed.")
                file_hash = calculate_file_hash(str(f))
                create_or_update_job(DocumentJob(
                    file_hash=file_hash,
                    file_name=f.name,
                    status="FAILED",
                    error_message="Server crashed during processing"
                ))
                move_to_failed(str(f))
            except Exception as repair_err:
                log_error(f"Startup Sync: Could not repair file {f.name}: {repair_err}")
    except Exception as e:
        log_error(f"DB init failed (check credentials): {e}")


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open("static/index.html", "r") as f:
        return f.read()


# ── Invoice Upload ───────────────────────────────────────────────────────────

@app.post("/upload")
def upload_invoice(file: UploadFile = File(...)):
    """Upload and immediately process a single invoice."""
    try:
        # Sanitize filename to prevent path traversal attacks
        safe_name = Path(file.filename).name
        ext = Path(safe_name).suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            raise HTTPException(400, f"Unsupported format '{ext}'. Allowed: {SUPPORTED_FORMATS}")

        dest = os.path.join(PENDING_DIR, safe_name)
        with open(dest, "wb") as f_out:
            shutil.copyfileobj(file.file, f_out)

        # Synchronous Level 1 Duplicate Check
        file_hash = calculate_file_hash(dest)
        is_dup, level, reason = run_duplicate_checks(file_hash=file_hash)
        if is_dup:
            if os.path.exists(dest):
                os.remove(dest)
            # Create a DUPLICATE job instantly so UI syncs correctly
            create_or_update_job(DocumentJob(
                file_hash=file_hash, 
                file_name=file.filename, 
                status="DUPLICATE", 
                stage="DUPLICATE", 
                progress=100, 
                error_message=reason
            ))
            return {"file": file.filename, "status": "DUPLICATE", "detail": reason}
            
        create_or_update_job(DocumentJob(file_hash=file_hash, file_name=file.filename, status="PENDING"))

        result = process_single_invoice(dest)
        return result
    except Exception as e:
        log_error(f"Global upload crash: {e}")
        return {"file": getattr(file, "filename", "Unknown"), "status": "FAILED", "detail": f"Server crash: {str(e)}"}


@app.post("/bulk-upload")
def bulk_upload(files: List[UploadFile] = File(...)):
    """Upload multiple invoices and process them synchronously."""
    try:
        results = []
        for upload in files:
            try:
                # Sanitize filename
                safe_name = Path(upload.filename).name
                ext = Path(safe_name).suffix.lower()
                if ext not in SUPPORTED_FORMATS:
                    results.append({"file": upload.filename, "status": "FAILED", "detail": f"Unsupported format '{ext}'"})
                    continue
                dest = os.path.join(PENDING_DIR, safe_name)
                with open(dest, "wb") as f_out:
                    shutil.copyfileobj(upload.file, f_out)
                
                file_hash = calculate_file_hash(dest)
                is_dup, level, reason = run_duplicate_checks(file_hash=file_hash)
                if is_dup:
                    if os.path.exists(dest):
                        os.remove(dest)
                    create_or_update_job(DocumentJob(
                        file_hash=file_hash, 
                        file_name=upload.filename, 
                        status="DUPLICATE", 
                        stage="DUPLICATE", 
                        progress=100, 
                        error_message=reason
                    ))
                    results.append({"file": upload.filename, "status": "DUPLICATE", "detail": reason})
                else:
                    create_or_update_job(DocumentJob(file_hash=file_hash, file_name=upload.filename, status="PENDING"))
                    # Process synchronously to prevent Vercel Serverless background tasks termination
                    res = process_single_invoice(dest)
                    results.append(res)
            except Exception as e:
                log_error(f"Failed to process file {upload.filename}: {e}")
                results.append({"file": upload.filename, "status": "FAILED", "detail": str(e)})

        return {"total": len(results), "results": results}
    except Exception as e:
        log_error(f"Global bulk-upload crash: {e}")
        return {"status": "FAILED", "detail": f"Server crash: {str(e)}"}


@app.post("/process-folder")
def process_folder():
    """Process all invoices already present in the pending/ folder synchronously."""
    from services.file_handler import scan_pending_invoices
    try:
        pending = scan_pending_invoices()
        if not pending:
            return {"total": 0, "results": []}

        results = []
        for p in pending:
            file_name = Path(p).name
            file_hash = calculate_file_hash(p)
            job = get_job_by_hash(file_hash)
            if job and job.get("status") == "PROCESSED":
                if os.path.exists(p):
                    os.remove(p)
                results.append({"file": file_name, "status": "DUPLICATE", "detail": "Already processed"})
            else:
                create_or_update_job(DocumentJob(file_hash=file_hash, file_name=file_name, status="PENDING"))
                # Process synchronously to prevent Vercel Serverless background tasks termination
                res = process_single_invoice(p)
                results.append(res)

        return {"total": len(results), "results": results}
    except Exception as e:
        log_error(f"Global process-folder crash: {e}")
        return {"status": "FAILED", "detail": f"Server crash: {str(e)}"}


# ── Invoice Queries ───────────────────────────────────────────────────────────

@app.get("/invoices")
def list_invoices(q: Optional[str] = None):
    if q:
        return search_invoices(q)
    return get_all_invoices()


@app.get("/invoice/{invoice_id}")
def get_invoice(invoice_id: str):
    row = get_invoice_by_id(invoice_id)
    if not row:
        raise HTTPException(404, "Invoice not found.")
    return row


# ── Jobs & Stats ──────────────────────────────────────────────────────────────

@app.get("/jobs")
def get_jobs():
    from services.database import get_all_jobs
    return get_all_jobs()

@app.post("/retry/{file_hash}")
def retry_job(file_hash: str):
    from services.database import get_db
    from services.file_handler import move_from_failed_to_pending
    db = get_db()
    job_ref = db.collection("document_jobs").document(file_hash)
    job_doc = job_ref.get()
    if not job_doc.exists:
        raise HTTPException(404, "Job not found")
    
    data = job_doc.to_dict()
    file_name = data.get("file_name")
    
    # Move file and reset state
    try:
        new_path = move_from_failed_to_pending(file_name)
        create_or_update_job(DocumentJob(
            file_hash=file_hash,
            file_name=file_name,
            status="QUEUED",
            stage="PENDING",
            progress=0
        ))
        res = process_single_invoice(new_path)
        return {"status": "success", "message": "Job retried synchronously", "result": res}
    except Exception as e:
        raise HTTPException(500, f"Retry failed: {e}")

@app.delete("/delete/{file_hash}")
def delete_job(file_hash: str):
    from services.database import get_db
    from config.db_config import PENDING_DIR, PROCESSING_DIR, PROCESSED_DIR, FAILED_DIR
    db = get_db()
    job_ref = db.collection("document_jobs").document(file_hash)
    doc = job_ref.get()
    if not doc.exists:
        raise HTTPException(404, "Job not found")
    
    data = doc.to_dict()
    file_name = data.get("file_name")
    
    if file_name:
        for d in [PENDING_DIR, PROCESSING_DIR, PROCESSED_DIR, FAILED_DIR]:
            path = os.path.join(d, file_name)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    log_error(f"Failed to delete orphaned file {path}: {e}")
    
    # Also delete the associated invoice if it exists
    invoice_id = data.get("invoice_id")
    if invoice_id:
        try:
            db.collection("invoices").document(invoice_id).delete()
        except Exception as e:
            log_error(f"Failed to delete invoice {invoice_id}: {e}")
            
    # And delete any related logs (we can query processing_logs by file_name if we wanted, but there's no log ID saved directly in job. Actually let's just delete the job and invoice)

    job_ref.delete()
    return {"status": "success", "message": "Job deleted"}

@app.get("/stats")
def stats():
    try:
        return get_stats()
    except Exception as e:
        return {"error": str(e), "total_invoices": 0, "grand_total_amount": 0, "processing_summary": {}}

@app.get("/stream")
def stream(request: Request):
    q = queue.Queue()
    from services.database import get_all_invoices, get_all_jobs, get_stats
    try:
        invoices = get_all_invoices()
        jobs = get_all_jobs()
        stats = get_stats()
        q.put_nowait(json.dumps({"type": "invoices", "data": invoices}))
        q.put_nowait(json.dumps({"type": "jobs", "data": jobs}))
        q.put_nowait(json.dumps({"type": "stats", "data": stats}))
    except Exception as e:
        log_error(f"Failed to populate initial stream data: {e}")
        
    streamer.add_queue(q)
    
    def event_generator():
        try:
            while True:
                try:
                    msg = q.get(timeout=15.0)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        except GeneratorExit:
            log_info("FirestoreStreamer: SSE client disconnected (GeneratorExit)")
        except Exception as e:
            log_info(f"FirestoreStreamer: SSE client disconnected: {e}")
        finally:
            streamer.discard_queue(q)
            
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Access-Control-Allow-Origin": "*"
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
