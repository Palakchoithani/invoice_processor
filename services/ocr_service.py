import os
import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image
import pytesseract

from services.logger import log_info, log_error
from services.ai.ai_router import AIRouter

# Initialize the Router
ai_router = AIRouter()

# ==========================================================
# LOCAL TEXT EXTRACTION (OCR)
# ==========================================================

def load_image(file_path: str) -> Image.Image:
    return Image.open(file_path).convert("RGB")

def extract_text_from_pdf(file_path: str, max_pages: int = 5) -> str:
    """
    Tries to extract native text from a PDF. If empty (scanned PDF),
    falls back to rasterizing pages and using Tesseract OCR.
    """
    doc = fitz.open(file_path)
    if not doc:
        raise ValueError("PDF contains no pages")
    
    num_pages = min(len(doc), max_pages)
    full_text = ""
    
    for i in range(num_pages):
        page = doc.load_page(i)
        page_text = page.get_text()
        
        # If native text exists, append it
        if page_text.strip():
            full_text += page_text + "\n"
        else:
            # Fallback: OCR the scanned page
            pix = page.get_pixmap(dpi=200)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data)).convert("RGB")
            try:
                ocr_text = pytesseract.image_to_string(img)
                full_text += ocr_text + "\n"
            except Exception as e:
                log_error(f"Tesseract OCR failed on PDF page {i}: {e}")
                
    return full_text.strip()

def extract_text_from_image(file_path: str) -> str:
    """Uses Tesseract to extract text from a static image."""
    img = load_image(file_path)
    try:
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        log_error(f"Tesseract OCR failed on image: {e}")
        return ""

# ==========================================================
# MAIN ROUTING FUNCTION
# ==========================================================

def extract_invoice_data(file_path: str) -> dict:
    file_path = str(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    extension = Path(file_path).suffix.lower()
    log_info(f"Processing invoice: {file_path}")

    # 1. Local OCR Pre-processing
    if extension == ".pdf":
        invoice_text = extract_text_from_pdf(file_path)
    elif extension in [".png", ".jpg", ".jpeg", ".webp"]:
        invoice_text = extract_text_from_image(file_path)
    else:
        raise ValueError(f"Unsupported file type: {extension}")

    if not invoice_text:
        raise RuntimeError("Local OCR failed to extract any text from the document.")

    log_info("OCR successful. Routing to AI layer...")

    # 2. Pass to AI Router
    extracted_data = ai_router.route_extraction(invoice_text)

    if not extracted_data:
        raise RuntimeError("AI router returned empty extraction data.")

    log_info(f"Final Data: {extracted_data}")
    return extracted_data, invoice_text
