import re
from typing import Tuple
from models.invoice_model import Invoice

GST_REGEX = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)


def validate_invoice(invoice: Invoice) -> Tuple[bool, str]:
    """
    Returns (is_valid, reason).
    reason is empty string on success.
    """
    if not invoice.invoice_number or not invoice.invoice_number.strip():
        return False, "Invoice number is missing."

    if invoice.total_amount is None:
        return False, "Total amount is missing."

    if invoice.total_amount <= 0:
        return False, f"Total amount must be > 0 (got {invoice.total_amount})."

    if invoice.invoice_date is None:
        return False, "Invoice date is missing or could not be parsed."

    if invoice.gst_number and not GST_REGEX.match(invoice.gst_number.upper()):
        # Warn but don't reject — many international invoices use non-GST tax IDs
        pass  # soft warning only

    return True, ""
