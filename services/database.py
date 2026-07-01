import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from config.db_config import FIREBASE_KEY_PATH
from models.invoice_model import Invoice, DocumentJob
from services.logger import log_info, log_error

_db = None

def get_db():
    global _db
    if _db is not None:
        return _db
    try:
        # Check if the app is already initialized
        if not firebase_admin._apps:
            import json
            firebase_json = os.getenv("FIREBASE_JSON")
            if firebase_json:
                try:
                    # Initialize from raw JSON string (Render environment variable)
                    cred_dict = json.loads(firebase_json)
                    cred = credentials.Certificate(cred_dict)
                    firebase_admin.initialize_app(cred)
                except Exception as parse_e:
                    log_error(f"Failed to parse FIREBASE_JSON env var: {parse_e}")
                    raise ValueError(f"Your FIREBASE_JSON environment variable is invalid or corrupted. Please copy-paste it carefully! Error: {parse_e}")
            elif os.path.exists(FIREBASE_KEY_PATH):
                cred = credentials.Certificate(FIREBASE_KEY_PATH)
                firebase_admin.initialize_app(cred)
            else:
                # Fallback
                firebase_admin.initialize_app()
        _db = firestore.client()
        log_info("Firebase initialized successfully.")
        return _db
    except Exception as e:
        log_error(f"Cannot initialize Firebase: {e}")
        raise ConnectionError(f"Firebase Init Error: {e}")

def init_db():
    """Initialize Firebase App (Collections are created implicitly in Firestore)."""
    get_db()

def normalize_invoice_number(inv: str) -> str:
    import re
    if not inv: return ""
    return re.sub(r'[^A-Z0-9]', '', str(inv).upper())

def save_invoice(invoice: Invoice) -> str:
    """Insert invoice into DB, return document id."""
    db = get_db()
    data = {
        "invoice_number": invoice.invoice_number,
        "normalized_invoice_number": normalize_invoice_number(invoice.invoice_number),
        "vendor_name": invoice.vendor_name,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "gst_number": invoice.gst_number,
        "subtotal": float(invoice.subtotal) if invoice.subtotal else 0.0,
        "tax_amount": float(invoice.tax_amount) if invoice.tax_amount else 0.0,
        "discount_amount": float(invoice.discount_amount) if invoice.discount_amount else 0.0,
        "shipping_charges": float(invoice.shipping_charges) if invoice.shipping_charges else 0.0,
        "packing_charges": float(invoice.packing_charges) if invoice.packing_charges else 0.0,
        "handling_charges": float(invoice.handling_charges) if invoice.handling_charges else 0.0,
        "insurance_charges": float(invoice.insurance_charges) if invoice.insurance_charges else 0.0,
        "other_charges": float(invoice.other_charges) if invoice.other_charges else 0.0,
        "round_off": float(invoice.round_off) if invoice.round_off else 0.0,
        "total_amount": float(invoice.total_amount) if invoice.total_amount else 0.0,
        "file_name": invoice.file_name,
        "file_hash": invoice.file_hash,
        "ocr_fingerprint": invoice.ocr_fingerprint,
        "line_items": invoice.line_items or [],
        "confidence_score": float(invoice.confidence_score),
        "validation_logs": invoice.validation_logs or [],
        "processing_time": invoice.processing_time.isoformat() if invoice.processing_time else datetime.now().isoformat(),
        "created_at": datetime.now().isoformat()
    }
    _, doc_ref = db.collection("invoices").add(data)
    log_info(f"Saved invoice {invoice.invoice_number} (id={doc_ref.id})")
    return doc_ref.id

def get_job_by_hash(file_hash: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    doc = db.collection("document_jobs").document(file_hash).get()
    if doc.exists:
        return doc.to_dict()
    return None

def create_or_update_job(job: DocumentJob):
    db = get_db()
    data = job.to_dict()
    # Remove None values so we don't overwrite with nulls unnecessarily if we are just updating status
    update_data = {k: v for k, v in data.items() if v is not None}
    db.collection("document_jobs").document(job.file_hash).set(update_data, merge=True)
    log_info(f"Updated job {job.file_hash} to status {job.status}")

def get_all_invoices() -> List[Dict[str, Any]]:
    db = get_db()
    docs = db.collection("invoices").order_by("created_at", direction=firestore.Query.DESCENDING).get()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

def get_invoice_by_id(invoice_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    doc = db.collection("invoices").document(invoice_id).get()
    if doc.exists:
        return {"id": doc.id, **doc.to_dict()}
    return None

def search_invoices(query: str) -> List[Dict[str, Any]]:
    # In-memory search as Firestore native doesn't support FULLTEXT LIKE '%query%'
    db = get_db()
    docs = db.collection("invoices").order_by("created_at", direction=firestore.Query.DESCENDING).get()
    results = []
    q_lower = query.lower()
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        
        # Check against text fields
        inv_num = (data.get("invoice_number") or "").lower()
        ven_name = (data.get("vendor_name") or "").lower()
        inv_date = (data.get("invoice_date") or "").lower()
        
        if q_lower in inv_num or q_lower in ven_name or q_lower in inv_date:
            results.append(data)
            
    return results

def get_all_jobs() -> List[Dict[str, Any]]:
    """Return all jobs for the realtime dashboard table."""
    db = get_db()
    docs = db.collection("document_jobs").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(500).get()
    results = []
    for doc in docs:
        d = doc.to_dict()
        results.append(d)
    return results

def get_stats() -> Dict[str, Any]:
    db = get_db()
    
    docs = db.collection("document_jobs").get()
    
    total_invoices = len(docs)
    processed = 0
    failed = 0
    processing = 0
    pending = 0
    queued = 0
    duplicates = 0
    grand_total = 0.0
    
    for doc in docs:
        data = doc.to_dict()
        st = data.get("status")
        if st == "PROCESSED" or st == "SUCCESS":
            processed += 1
            grand_total += float(data.get("total_amount") or 0.0)
        elif st == "FAILED":
            failed += 1
        elif st == "DUPLICATE":
            duplicates += 1
        elif st == "PROCESSING":
            processing += 1
        elif st == "PENDING":
            pending += 1
        elif st == "QUEUED":
            queued += 1
            
    return {
        "total_invoices": total_invoices,
        "grand_total_amount": grand_total,
        "processing_summary": {
            "SUCCESS": processed,
            "FAILED": failed,
            "DUPLICATE": duplicates,
            "PROCESSING": processing,
            "PENDING": pending,
            "QUEUED": queued
        }
    }
