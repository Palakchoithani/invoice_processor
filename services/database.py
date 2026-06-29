import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from config.db_config import FIREBASE_KEY_PATH
from models.invoice_model import Invoice, ProcessingLog
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

def check_duplicate(invoice_number: str) -> bool:
    """Returns True if invoice_number already exists in DB."""
    db = get_db()
    docs = db.collection("invoices").where(filter=firestore.FieldFilter("invoice_number", "==", invoice_number)).limit(1).get()
    return len(docs) > 0

def save_invoice(invoice: Invoice) -> str:
    """Insert invoice into DB, return document id."""
    db = get_db()
    data = {
        "invoice_number": invoice.invoice_number,
        "vendor_name": invoice.vendor_name,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "gst_number": invoice.gst_number,
        "subtotal": float(invoice.subtotal) if invoice.subtotal else 0.0,
        "tax_amount": float(invoice.tax_amount) if invoice.tax_amount else 0.0,
        "total_amount": float(invoice.total_amount) if invoice.total_amount else 0.0,
        "file_name": invoice.file_name,
        "line_items": invoice.line_items or [],
        "processing_time": invoice.processing_time.isoformat() if invoice.processing_time else datetime.now().isoformat(),
        "created_at": datetime.now().isoformat()
    }
    _, doc_ref = db.collection("invoices").add(data)
    log_info(f"Saved invoice {invoice.invoice_number} (id={doc_ref.id})")
    return doc_ref.id

def write_log(log: ProcessingLog):
    """Insert a processing log record."""
    db = get_db()
    data = {
        "file_name": log.file_name,
        "status": log.status,
        "error_message": log.error_message,
        "processed_at": datetime.now().isoformat()
    }
    db.collection("processing_logs").add(data)

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

def get_all_logs() -> List[Dict[str, Any]]:
    db = get_db()
    docs = db.collection("processing_logs").order_by("processed_at", direction=firestore.Query.DESCENDING).limit(200).get()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

def get_stats() -> Dict[str, Any]:
    db = get_db()
    
    # Calculate invoice stats
    invoices = db.collection("invoices").get()
    total_invoices = len(invoices)
    grand_total = sum((doc.to_dict().get("total_amount") or 0.0) for doc in invoices)
    
    # Calculate log stats
    logs = db.collection("processing_logs").get()
    status_map = {}
    for doc in logs:
        st = doc.to_dict().get("status")
        if st:
            status_map[st] = status_map.get(st, 0) + 1
            
    return {
        "total_invoices": total_invoices,
        "grand_total_amount": float(grand_total),
        "processing_summary": status_map,
    }
