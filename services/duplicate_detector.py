import re
import hashlib
from typing import Tuple, Optional, Any, Dict
from firebase_admin import firestore
from services.database import get_db, normalize_invoice_number
from services.logger import log_info, log_warning

def generate_ocr_fingerprint(invoice_text: str) -> str:
    """
    Generates a normalized SHA-256 fingerprint from OCR text.
    Removes whitespace, punctuation, and converts to lowercase to catch 
    identical contents regardless of minor formatting or scanning artifacts.
    """
    if not invoice_text:
        return ""
    
    # Convert to lowercase
    text = invoice_text.lower()
    # Remove all non-alphanumeric characters (spaces, punctuation, etc.)
    text = re.sub(r'[^a-z0-9]', '', text)
    
    # Hash the resulting normalized string
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def check_duplicate_level_1_hash(file_hash: str) -> bool:
    """Level 1: Exact File Hash match."""
    db = get_db()
    docs = db.collection("invoices").where(filter=firestore.FieldFilter("file_hash", "==", file_hash)).limit(1).get()
    return len(docs) > 0

def check_duplicate_level_2_metadata(invoice_number: str, vendor_name: str, invoice_date: str) -> bool:
    """Level 2: Exact Invoice Number, Vendor, and Date match."""
    if not invoice_number or not vendor_name:
        return False
        
    db = get_db()
    norm_inv = normalize_invoice_number(invoice_number)
    
    # Query by normalized invoice number first
    query = db.collection("invoices").where(filter=firestore.FieldFilter("normalized_invoice_number", "==", norm_inv))
    docs = query.get()
    
    # Refine in-memory to check vendor and date
    v_target = vendor_name.lower().strip()
    d_target = invoice_date.strip() if invoice_date else ""
    
    for doc in docs:
        data = doc.to_dict()
        v_db = (data.get("vendor_name") or "").lower().strip()
        d_db = (data.get("invoice_date") or "").strip()
        
        # If invoice number matches (already filtered by query), and vendor matches, and date matches
        if v_db == v_target and d_db == d_target:
            return True
            
    return False

def check_duplicate_level_3_content(vendor_name: str, invoice_date: str, total_amount: float, line_items_count: int) -> bool:
    """Level 3: Heuristic content match (Vendor + Date + Amount + Line Items length)."""
    if not vendor_name or total_amount is None:
        return False
        
    db = get_db()
    # Query by exact total_amount
    query = db.collection("invoices").where(filter=firestore.FieldFilter("total_amount", "==", float(total_amount)))
    docs = query.get()
    
    v_target = vendor_name.lower().strip()
    d_target = invoice_date.strip() if invoice_date else ""
    
    for doc in docs:
        data = doc.to_dict()
        v_db = (data.get("vendor_name") or "").lower().strip()
        d_db = (data.get("invoice_date") or "").strip()
        items_db = data.get("line_items") or []
        
        if v_db == v_target and d_db == d_target and len(items_db) == line_items_count:
            return True
            
    return False

def check_duplicate_level_4_ocr(ocr_fingerprint: str) -> bool:
    """Level 4: Exact OCR fingerprint match."""
    if not ocr_fingerprint:
        return False
        
    db = get_db()
    docs = db.collection("invoices").where(filter=firestore.FieldFilter("ocr_fingerprint", "==", ocr_fingerprint)).limit(1).get()
    return len(docs) > 0

def run_duplicate_checks(
    file_hash: Optional[str] = None,
    invoice_number: Optional[str] = None,
    vendor_name: Optional[str] = None,
    invoice_date: Optional[str] = None,
    total_amount: Optional[float] = None,
    line_items_count: int = 0,
    ocr_fingerprint: Optional[str] = None
) -> Tuple[bool, str, str]:
    """
    Runs all 4 levels of duplicate checks.
    Returns: (is_duplicate, match_level_name, reason)
    """
    
    # LEVEL 1
    if file_hash and check_duplicate_level_1_hash(file_hash):
        reason = "File Hash exactly matches a previously processed invoice."
        log_warning(f"Duplicate Level 1 Triggered: {reason}")
        return True, "Level 1 (File Hash)", reason
        
    # LEVEL 2
    if invoice_number and vendor_name and check_duplicate_level_2_metadata(invoice_number, vendor_name, invoice_date):
        reason = f"Invoice Number '{invoice_number}' for vendor '{vendor_name}' on date '{invoice_date}' already exists."
        log_warning(f"Duplicate Level 2 Triggered: {reason}")
        return True, "Level 2 (Metadata)", reason
        
    # LEVEL 3
    if vendor_name and total_amount is not None and check_duplicate_level_3_content(vendor_name, invoice_date, total_amount, line_items_count):
        reason = f"An invoice for vendor '{vendor_name}' on date '{invoice_date}' with total '{total_amount}' and {line_items_count} items already exists."
        log_warning(f"Duplicate Level 3 Triggered: {reason}")
        return True, "Level 3 (Content Match)", reason
        
    # LEVEL 4
    if ocr_fingerprint and check_duplicate_level_4_ocr(ocr_fingerprint):
        reason = "OCR Fingerprint matches a previously processed invoice (possible rescan or formatting change)."
        log_warning(f"Duplicate Level 4 Triggered: {reason}")
        return True, "Level 4 (OCR Fingerprint)", reason
        
    return False, "None", "Unique invoice"
