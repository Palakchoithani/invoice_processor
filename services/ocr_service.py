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
    # 1. Total Amount (Exclude Subtotal, handle Rupee ₹ symbol and newlines)
    total_match = re.search(r"(?i)(?<!sub\s)(?<!sub)(?:total|amount due|balance due|grand total)[\s\n:]*[\$Rs\₹\.]*\s*([\d,]+\.\d{2})", text)
    total_amount = float(total_match.group(1).replace(",", "")) if total_match else None

    # 2. Tax Amount (GST, IGST, SGST, CGST, VAT, TAX)
    tax_match = re.search(r"(?i)(?:tax|gst|igst|cgst|sgst|vat)[\s\n:]*[\$Rs\₹\.]*\s*([\d,]+\.\d{2})", text)
    tax_amount = float(tax_match.group(1).replace(",", "")) if tax_match else None

    # 3. Invoice Date (Handle textual months and standard numeric formats)
    invoice_date = None
    # Match: 12 Oct 2023, 12th October 2023, Oct 12, 2023
    alpha_date = re.search(r"(?i)\b(\d{1,2}(?:st|nd|rd|th)?[\s,-]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,-]+\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,-]+\d{1,2}(?:st|nd|rd|th)?[\s,-]+\d{2,4})\b", text)
    if alpha_date:
        invoice_date = alpha_date.group(1).strip()
    else:
        # Match DD/MM/YYYY, MM/DD/YYYY, or YYYY-MM-DD
        date_match = re.search(r"(?i)(?:date)[\s\n:]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})", text)
        if not date_match:
            date_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b", text)
        invoice_date = date_match.group(1) if date_match else None

    # 4. Invoice Number (Require word boundary, prevent matching the word 'Invoice' itself)
    inv_match = re.search(r"(?i)\b(?:invoice|inv)\b\s*(?:no|#|num)?[\s\n.:]*((?!invoice\b)[A-Z0-9-/]{4,})", text)
    invoice_number = inv_match.group(1) if inv_match else None

    # 5. Vendor Name (Look for company suffixes, or fallback)
    vendor_name = None
    company_match = re.search(r"(?i)((?:For\s+)?([A-Za-z0-9&\s.,]+(?:Private Limited|Pvt\.?\s*Ltd\.?|LLP|Inc\.?|LLC|Corporation|Corp\.?|Limited|Ltd\.?)))", text)
    if company_match:
        vendor_name = company_match.group(2).strip()
        # Clean up any preceding garbage from multiple lines matching
        vendor_name = vendor_name.split("\n")[-1].strip()
        if vendor_name.lower().startswith("for "):
            vendor_name = vendor_name[4:].strip()
    else:
        # Fallback to the first non-empty, non-trivial line
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 4]
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
