import os
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config.db_config import PENDING_DIR, PROCESSING_DIR, FAILED_DIR, SUPPORTED_FORMATS
from services.processor import process_single_invoice
from services.database import (
    init_db, get_all_invoices, get_invoice_by_id,
    search_invoices, get_stats, get_job_by_hash, create_or_update_job
)
from models.invoice_model import DocumentJob
from services.file_handler import ensure_dirs, calculate_file_hash, move_to_failed
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

# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    ensure_dirs()
    try:
        init_db()
        log_info("App started. DB ready.")
        # Startup Sync: Repair broken states
        # Any file left in processing/ was interrupted. Move to failed.
        for f in Path(PROCESSING_DIR).iterdir():
            if f.is_file():
                log_info(f"Startup Sync: Found interrupted file {f.name}. Moving to failed.")
                file_hash = calculate_file_hash(str(f))
                create_or_update_job(DocumentJob(
                    file_hash=file_hash,
                    file_name=f.name,
                    status="FAILED",
                    error_message="Server crashed during processing"
                ))
                move_to_failed(str(f))
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
        ext = Path(file.filename).suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            raise HTTPException(400, f"Unsupported format '{ext}'. Allowed: {SUPPORTED_FORMATS}")

        dest = os.path.join(PENDING_DIR, file.filename)
        with open(dest, "wb") as f_out:
            shutil.copyfileobj(file.file, f_out)

        # Pre-register PENDING state
        file_hash = calculate_file_hash(dest)
        job = get_job_by_hash(file_hash)
        if job and job.get("status") == "PROCESSED":
            return {"file": file.filename, "status": "DUPLICATE", "detail": "File has already been processed successfully"}
            
        create_or_update_job(DocumentJob(file_hash=file_hash, file_name=file.filename, status="PENDING"))

        result = process_single_invoice(dest)
        return result
    except Exception as e:
        log_error(f"Global upload crash: {e}")
        return {"file": getattr(file, "filename", "Unknown"), "status": "FAILED", "detail": f"Server crash: {str(e)}"}


def background_process_files(paths: List[str]):
    for p in paths:
        process_single_invoice(p)

@app.post("/bulk-upload")
def bulk_upload(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """Upload multiple invoices and process them in the background."""
    try:
        saved_paths = []
        results = []
        for upload in files:
            ext = Path(upload.filename).suffix.lower()
            if ext not in SUPPORTED_FORMATS:
                continue
            dest = os.path.join(PENDING_DIR, upload.filename)
            with open(dest, "wb") as f_out:
                shutil.copyfileobj(upload.file, f_out)
            
            file_hash = calculate_file_hash(dest)
            job = get_job_by_hash(file_hash)
            if job and job.get("status") == "PROCESSED":
                results.append({"file": upload.filename, "status": "DUPLICATE", "detail": "Already processed"})
            else:
                create_or_update_job(DocumentJob(file_hash=file_hash, file_name=upload.filename, status="PENDING"))
                saved_paths.append(dest)
                results.append({"file": upload.filename, "status": "QUEUED", "detail": "Added to processing queue"})

        background_tasks.add_task(background_process_files, saved_paths)

        return {"total": len(results), "results": results}
    except Exception as e:
        log_error(f"Global bulk-upload crash: {e}")
        return {"status": "FAILED", "detail": f"Server crash: {str(e)}"}


@app.post("/process-folder")
def process_folder(background_tasks: BackgroundTasks):
    """Process all invoices already present in the pending/ folder."""
    from services.file_handler import scan_pending_invoices
    try:
        pending = scan_pending_invoices()
        if not pending:
            return {"total": 0, "results": []}

        results = []
        valid_paths = []
        for p in pending:
            file_name = Path(p).name
            file_hash = calculate_file_hash(p)
            job = get_job_by_hash(file_hash)
            if job and job.get("status") == "PROCESSED":
                results.append({"file": file_name, "status": "DUPLICATE", "detail": "Already processed"})
            else:
                create_or_update_job(DocumentJob(file_hash=file_hash, file_name=file_name, status="PENDING"))
                valid_paths.append(p)
                results.append({"file": file_name, "status": "QUEUED", "detail": "Added to processing queue"})

        background_tasks.add_task(background_process_files, valid_paths)

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
def retry_job(file_hash: str, background_tasks: BackgroundTasks):
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
        background_tasks.add_task(process_single_invoice, new_path)
        return {"status": "success", "message": "Job queued for retry"}
    except Exception as e:
        raise HTTPException(500, f"Retry failed: {e}")

@app.delete("/delete/{file_hash}")
def delete_job(file_hash: str):
    from services.database import get_db
    db = get_db()
    job_ref = db.collection("document_jobs").document(file_hash)
    if not job_ref.get().exists:
        raise HTTPException(404, "Job not found")
    
    job_ref.delete()
    return {"status": "success", "message": "Job deleted"}

@app.get("/stats")
def stats():
    try:
        return get_stats()
    except Exception as e:
        return {"error": str(e), "total_invoices": 0, "grand_total_amount": 0, "processing_summary": {}}
