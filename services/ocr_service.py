import os
import re
from pathlib import Path
from typing import Optional
import fitz  # PyMuPDF

from services.logger import log_info, log_error, log_warning

def extract_text_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text("text") + "\n"
    return text

def parse_with_regex(text: str) -> dict:
    # 1. Total Amount
    total_match = re.search(r"(?i)(?:total|amount due|balance due)[\s:]*[\$Rs\.]*\s*([\d,]+\.\d{2})", text)
    total_amount = float(total_match.group(1).replace(",", "")) if total_match else None

    # 2. Tax Amount
    tax_match = re.search(r"(?i)(?:tax|gst|vat|cgst|sgst)[\s:]*[\$Rs\.]*\s*([\d,]+\.\d{2})", text)
    tax_amount = float(tax_match.group(1).replace(",", "")) if tax_match else None

    # 3. Invoice Date
    date_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", text)
    invoice_date = date_match.group(1) if date_match else None

    # 4. Invoice Number
    inv_match = re.search(r"(?i)(?:invoice|inv)\s*(?:no|#|num)?[\s.:]*([A-Z0-9-]{3,})", text)
    invoice_number = inv_match.group(1) if inv_match else None

    # 5. Vendor Name
    # Fallback to the first non-empty line
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    vendor_name = lines[0] if lines else None

    if vendor_name and len(vendor_name) > 100:
        vendor_name = vendor_name[:100]
        
    return {
        "invoice_number": invoice_number,
        "vendor_name": vendor_name,
        "invoice_date": invoice_date,
        "gst_number": None,
        "subtotal": None,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
        "line_items": []
    }

def extract_invoice_data(file_path: str) -> dict:
    file_path = str(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    extension = Path(file_path).suffix.lower()
    log_info(f"Processing invoice via local Regex parser: {file_path}")

    if extension == ".pdf":
        text = extract_text_from_pdf(file_path)
    else:
        raise ValueError(f"Image OCR is not supported in the local regex parser without Tesseract: {extension}")

    if not text.strip():
        raise ValueError("No text could be extracted from the document (likely a scanned image).")
        
    log_info(f"Extracted {len(text)} characters of text.")
    extracted_data = parse_with_regex(text)

    log_info(f"Final Regex Parsed Data: {extracted_data}")
    return extracted_data

if __name__ == "__main__":
    print("Local regex parser initialized.")
