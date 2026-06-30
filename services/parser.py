import re
from datetime import date, datetime
from typing import Optional, Tuple, List, Any
from models.invoice_model import Invoice
from services.logger import log_warning

DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
]

def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    log_warning(f"Could not parse date: '{raw}'")
    return None

def _normalize_ocr_amount(raw: Any) -> Optional[float]:
    """
    Normalizes messy OCR strings into clean floats.
    Handles 'O' vs '0', missing decimals, and European comma-decimals.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
        
    s = str(raw).strip()
    
    # 1. OCR Character replacements
    s = s.replace("O", "0").replace("o", "0")
    s = s.replace("l", "1").replace("I", "1")
    s = s.replace("S", "5").replace("s", "5")
    
    # 2. Strip currency symbols and letters
    s = re.sub(r"[^\d\,\.\-]", "", s)
    if not s:
        return None
        
    # 3. Detect European formats vs US formats
    # If the string has a comma and a period
    if "," in s and "." in s:
        comma_idx = s.rfind(",")
        dot_idx = s.rfind(".")
        if comma_idx > dot_idx:
            # European: 1.000,50 -> 1000.50
            s = s.replace(".", "").replace(",", ".")
        else:
            # US: 1,000.50 -> 1000.50
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        # It could be 1,000 (one thousand) or 100,50 (100 point 5)
        # If there are exactly 2 digits after the last comma, assume it's a European decimal
        parts = s.split(",")
        if len(parts[-1]) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
            
    # 4. Final cast
    try:
        val = float(s)
        # Reject mathematically impossible negative values
        return val if val >= 0 else None
    except ValueError:
        return None

def parse_invoice(raw_data: dict, file_name: str) -> Invoice:
    """
    ARITHMETIC ENGINE
    Converts raw OCR JSON into a typed Invoice object, completely rejecting
    LLM math and strictly recalculating every value from the ground up.
    """
    logs = []
    confidence_score = 1.0

    # 1. Extract raw line items
    raw_line_items = raw_data.get("line_items") or []
    validated_line_items = []
    calculated_subtotal = 0.0

    for idx, item in enumerate(raw_line_items):
        qty = _normalize_ocr_amount(item.get("quantity")) or 1.0
        price = _normalize_ocr_amount(item.get("unit_price")) or 0.0
        ocr_total = _normalize_ocr_amount(item.get("total")) or 0.0
        
        # NEVER trust the OCR total. Always calculate it mathematically.
        math_total = round(qty * price, 2)
        
        if ocr_total != math_total:
            logs.append(f"Line {idx+1} ({item.get('description')}): OCR Total {ocr_total} replaced by calculated {math_total} ({qty}x{price})")
            confidence_score -= 0.05
            
        validated_item = {
            "description": str(item.get("description", "Unknown Item")),
            "quantity": qty,
            "unit_price": price,
            "original_total": ocr_total,
            "total": math_total
        }
        validated_line_items.append(validated_item)
        calculated_subtotal += math_total

    calculated_subtotal = round(calculated_subtotal, 2)

    # 2. Extract Invoice Totals
    ocr_subtotal = _normalize_ocr_amount(raw_data.get("subtotal")) or 0.0
    ocr_tax = _normalize_ocr_amount(raw_data.get("tax_amount")) or 0.0
    ocr_discount = _normalize_ocr_amount(raw_data.get("discount_amount")) or 0.0
    ocr_grand_total = _normalize_ocr_amount(raw_data.get("total_amount")) or 0.0

    # 3. Subtotal Validation
    # If the calculated sum of line items disagrees with the OCR subtotal, we trust our math.
    if calculated_subtotal > 0 and ocr_subtotal != calculated_subtotal:
        logs.append(f"Subtotal Override: OCR {ocr_subtotal} replaced by Line Items Sum {calculated_subtotal}")
        confidence_score -= 0.1
        final_subtotal = calculated_subtotal
    else:
        # If there were no line items extracted, we are forced to trust the OCR subtotal
        final_subtotal = ocr_subtotal

    # 4. Grand Total Calculation
    # total = subtotal + tax - discount
    math_grand_total = round(final_subtotal + ocr_tax - ocr_discount, 2)
    
    if ocr_grand_total != math_grand_total:
        logs.append(f"Grand Total Override: OCR {ocr_grand_total} replaced by Math {math_grand_total} ({final_subtotal} + {ocr_tax} - {ocr_discount})")
        confidence_score -= 0.1
        final_grand_total = math_grand_total
    else:
        final_grand_total = ocr_grand_total

    # Bound confidence score
    confidence_score = max(0.0, min(1.0, confidence_score))

    return Invoice(
        invoice_number=raw_data.get("invoice_number") or None,
        vendor_name=raw_data.get("vendor_name") or None,
        invoice_date=_parse_date(raw_data.get("invoice_date")),
        gst_number=raw_data.get("gst_number") or None,
        subtotal=final_subtotal,
        tax_amount=ocr_tax,
        discount_amount=ocr_discount,
        total_amount=final_grand_total,
        file_name=file_name,
        line_items=validated_line_items,
        confidence_score=round(confidence_score, 2),
        validation_logs=logs,
        processing_time=datetime.now(),
    )
