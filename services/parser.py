import re
from datetime import date, datetime
from typing import Optional, Tuple, List, Any
from models.invoice_model import Invoice
from services.logger import log_warning

class MismatchException(Exception):
    def __init__(self, printed_total: float, calculated_total: float, gap: float, message: str):
        self.printed_total = printed_total
        self.calculated_total = calculated_total
        self.gap = gap
        super().__init__(message)

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

def parse_invoice(raw_data: dict, file_name: str, recovery_pass: bool = False) -> Invoice:
    """
    ARITHMETIC ENGINE
    Converts raw OCR JSON into a typed Invoice object, completely rejecting
    LLM math and strictly recalculating every value from the ground up.
    """
    validation_logs = []
    confidence_score = 1.0

    def deduct_confidence(amount: float, reason: str):
        nonlocal confidence_score
        confidence_score -= amount
        validation_logs.append(reason)

    # 1. Extract and Normalize Document-Level Fields
    ocr_subtotal = _normalize_ocr_amount(raw_data.get("subtotal")) or 0.0
    tax_amount = _normalize_ocr_amount(raw_data.get("tax_amount")) or 0.0
    discount_amount = _normalize_ocr_amount(raw_data.get("discount_amount")) or 0.0
    shipping_charges = _normalize_ocr_amount(raw_data.get("shipping_charges")) or 0.0
    packing_charges = _normalize_ocr_amount(raw_data.get("packing_charges")) or 0.0
    handling_charges = _normalize_ocr_amount(raw_data.get("handling_charges")) or 0.0
    insurance_charges = _normalize_ocr_amount(raw_data.get("insurance_charges")) or 0.0
    other_charges = _normalize_ocr_amount(raw_data.get("other_charges")) or 0.0
    round_off = _normalize_ocr_amount(raw_data.get("round_off")) or 0.0
    ocr_grand_total = _normalize_ocr_amount(raw_data.get("total_amount")) or 0.0

    # 2. Extract and Validate Line Items
    validated_line_items = []
    calculated_subtotal = 0.0

    for idx, item in enumerate(raw_data.get("line_items", [])):
        qty = _normalize_ocr_amount(item.get("quantity")) or 1.0
        unit_price = _normalize_ocr_amount(item.get("unit_price")) or 0.0
        ocr_item_total = _normalize_ocr_amount(item.get("total")) or 0.0
        
        # Check if LLM swapped unit price and total due to OCR column scrambling
        # If qty > 1, the unit price MUST be smaller than the total. If it's larger, they are swapped.
        if qty > 1 and unit_price > ocr_item_total and ocr_item_total > 0:
            validation_logs.append(f"Line {idx+1} ({item.get('description', 'Item')}): Swapped Unit Price ({unit_price}) and Total ({ocr_item_total}) to fix OCR column hallucination.")
            # Swap them
            temp = unit_price
            unit_price = ocr_item_total
            ocr_item_total = temp
            
        # Calculate true mathematical total
        math_item_total = qty * unit_price
        
        # Cross-check
        if ocr_item_total != math_item_total and math_item_total > 0:
            deduct_confidence(0.10, f"Line {idx+1} ({item.get('description', 'Item')}): OCR Total {ocr_item_total} replaced by calculated {math_item_total} ({qty}x{unit_price})")
            final_item_total = math_item_total
        else:
            final_item_total = ocr_item_total

        validated_line_items.append({
            "description": item.get("description", ""),
            "quantity": qty,
            "unit_price": unit_price,
            "total": final_item_total,
            "original_total": ocr_item_total if ocr_item_total != final_item_total else None
        })
        
        calculated_subtotal += final_item_total

    # 3. Validate Subtotal
    final_subtotal = ocr_subtotal
    if len(validated_line_items) > 0 and abs(ocr_subtotal - calculated_subtotal) > 0.01:
        deduct_confidence(0.15, f"Subtotal Override: OCR {ocr_subtotal} replaced by Line Items Sum {calculated_subtotal}")
        final_subtotal = calculated_subtotal

    # 4. Validate Grand Total (0.01 Tolerance)
    misc_charges = shipping_charges + packing_charges + handling_charges + insurance_charges + other_charges
    calculated_grand_total = final_subtotal + tax_amount - discount_amount + misc_charges + round_off
    
    final_total = ocr_grand_total
    
    # Check if the extracted OCR total matches our math (with 0.01 tolerance)
    if abs(ocr_grand_total - calculated_grand_total) <= 0.01:
        # Trust the printed invoice total
        if ocr_grand_total > 0:
            validation_logs.append(f"Printed total {ocr_grand_total} matched calculated total {calculated_grand_total} (Accepted)")
        final_total = ocr_grand_total
    else:
        # Mismatch detected! 
        difference = abs(ocr_grand_total - calculated_grand_total)
        
        if not recovery_pass and ocr_grand_total > 0:
            # Trigger Multi-Pass Recovery Pipeline on the first pass
            raise MismatchException(
                printed_total=ocr_grand_total,
                calculated_total=calculated_grand_total,
                gap=round(difference, 2),
                message=f"Discrepancy Detected. Printed: {ocr_grand_total}, Calculated: {calculated_grand_total}. Missing: {round(difference, 2)}"
            )
            
        # If we are here, we are on the recovery pass (or printed total was 0)
        # We DO NOT block extraction anymore. The user wants the invoice saved even if math is wildly off.
        # We ALWAYS trust the printed total if it exists, because the printed document is the source of truth.
        if ocr_grand_total > 0:
            deduct_confidence(0.50, f"Massive Discrepancy: Printed Total {ocr_grand_total} does not match Math {calculated_grand_total}. Trusting Printed Total but flagging for review.")
            final_total = ocr_grand_total
        else:
            deduct_confidence(0.25, f"Grand Total Missing: Falling back to Math Total {calculated_grand_total}")
            final_total = calculated_grand_total

    return Invoice(
        invoice_number=raw_data.get("invoice_number", ""),
        vendor_name=raw_data.get("vendor_name", ""),
        invoice_date=_parse_date(raw_data.get("invoice_date", "")),
        gst_number=raw_data.get("gst_number", ""),
        subtotal=final_subtotal,
        tax_amount=tax_amount,
        discount_amount=discount_amount,
        shipping_charges=shipping_charges,
        packing_charges=packing_charges,
        handling_charges=handling_charges,
        insurance_charges=insurance_charges,
        other_charges=other_charges,
        round_off=round_off,
        total_amount=final_total,
        file_name=file_name,
        line_items=validated_line_items,
        confidence_score=round(max(0.0, confidence_score), 2),
        validation_logs=validation_logs,
        extraction_logs=raw_data.get("extraction_logs", []),
        processing_time=datetime.now(),
    )
