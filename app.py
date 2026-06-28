import os
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config.db_config import INVOICES_DIR, SUPPORTED_FORMATS
from services.processor import process_single_invoice, process_all_invoices
from services.database import (
    init_db, get_all_invoices, get_invoice_by_id,
    search_invoices, get_all_logs, get_stats,
)
from services.file_handler import ensure_dirs
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
    except Exception as e:
        log_error(f"DB init failed (check credentials): {e}")


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open("static/index.html", "r") as f:
        return f.read()


# ── Invoice Upload ───────────────────────────────────────────────────────────

@app.post("/upload")
def upload_invoice(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload and immediately process a single invoice."""
    try:
        ext = Path(file.filename).suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            raise HTTPException(400, f"Unsupported format '{ext}'. Allowed: {SUPPORTED_FORMATS}")

        dest = os.path.join(INVOICES_DIR, file.filename)
        with open(dest, "wb") as f_out:
            shutil.copyfileobj(file.file, f_out)

        result = process_single_invoice(dest)
        return result
    except Exception as e:
        log_error(f"Global upload crash: {e}")
        return {"status": "FAILED", "detail": f"Server crash: {str(e)}"}


def _run_bulk_background(saved_paths: List[str]):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        for _ in executor.map(process_single_invoice, saved_paths):
            pass

@app.post("/bulk-upload")
def bulk_upload(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """Upload multiple invoices and process them in the background."""
    try:
        saved_paths = []
        for upload in files:
            ext = Path(upload.filename).suffix.lower()
            if ext not in SUPPORTED_FORMATS:
                continue
            dest = os.path.join(INVOICES_DIR, upload.filename)
            with open(dest, "wb") as f_out:
                shutil.copyfileobj(upload.file, f_out)
            saved_paths.append(dest)

        background_tasks.add_task(_run_bulk_background, saved_paths)

        results = [{"file": Path(p).name, "status": "QUEUED", "detail": "Processing in background"} for p in saved_paths]
        return {"total": len(results), "results": results}
    except Exception as e:
        log_error(f"Global bulk-upload crash: {e}")
        return {"status": "FAILED", "detail": f"Server crash: {str(e)}"}


@app.post("/process-folder")
def process_folder():
    """Process all invoices already present in the invoices/ folder."""
    from services.processor import get_all_pending
    from concurrent.futures import ThreadPoolExecutor
    
    pending = get_all_pending()
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for result in executor.map(process_single_invoice, pending):
            results.append(result)
            
    return {"total": len(results), "results": results}


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


# ── Logs & Stats ──────────────────────────────────────────────────────────────

@app.get("/logs")
def get_logs():
    return get_all_logs()


@app.get("/stats")
def stats():
    try:
        return get_stats()
    except Exception as e:
        return {"error": str(e), "total_invoices": 0, "grand_total_amount": 0, "processing_summary": {}}
