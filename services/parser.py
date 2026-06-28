import re
from datetime import date, datetime
from typing import Optional
from models.invoice_model import Invoice
from services.logger import log_warning

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
]


def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    log_warning(f"Could not parse date: '{raw}'")
    return None


def _parse_amount(raw) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    # Remove currency symbols and commas
    cleaned = re.sub(r"[₹$€£,\s]", "", str(raw))
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_invoice(raw_data: dict, file_name: str) -> Invoice:
    """Convert raw Gemini extraction dict into a typed Invoice object."""
    return Invoice(
        invoice_number=raw_data.get("invoice_number") or None,
        vendor_name=raw_data.get("vendor_name") or None,
        invoice_date=_parse_date(raw_data.get("invoice_date")),
        gst_number=raw_data.get("gst_number") or None,
        subtotal=_parse_amount(raw_data.get("subtotal")),
        tax_amount=_parse_amount(raw_data.get("tax_amount")),
        total_amount=_parse_amount(raw_data.get("total_amount")),
        file_name=file_name,
        processing_time=datetime.now(),
    )
