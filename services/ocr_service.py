import os
import io
import json
import re
import time

from pathlib import Path
from typing import Optional

import google.generativeai as genai
import fitz  # PyMuPDF
from PIL import Image

from services.logger import log_info, log_error, log_warning

# ==========================================================
# CONFIG
# ==========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = "gemini-2.5-flash"

EXTRACTION_PROMPT = """
You are an invoice extraction expert.

Analyze the provided invoice image and convert the data into the following JSON structure.

Return ONLY valid JSON.

{
  "invoice_number": null,
  "vendor_name": null,
  "invoice_date": null,
  "gst_number": null,
  "subtotal": null,
  "tax_amount": null,
  "total_amount": null
}

Rules:
- Return JSON only.
- No markdown.
- No explanations.
- Dates must be YYYY-MM-DD.
- Amounts must be numeric values.
- Missing values must be null.
"""


# ==========================================================
# IMAGE HELPERS
# ==========================================================

def load_image(file_path: str) -> Image.Image:
    return Image.open(file_path).convert("RGB")

def pdf_to_images(file_path: str, max_pages: int = 5) -> list[Image.Image]:
    doc = fitz.open(file_path)
    if not doc:
        raise ValueError("PDF contains no pages")
    
    images = []
    num_pages = min(len(doc), max_pages)
    for i in range(num_pages):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=200)
        img_data = pix.tobytes("png")
        images.append(Image.open(io.BytesIO(img_data)).convert("RGB"))
        
    return images

# ==========================================================
# JSON PARSER
# ==========================================================

def parse_json_response(text: str) -> dict:
    if not text:
        raise ValueError("Gemini returned empty response")
    
    text = text.strip()
    text = re.sub(r"^```json", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Invalid Gemini JSON:\n{text[:500]}")


# ==========================================================
# GEMINI STRUCTURING
# ==========================================================

def extract_from_images(images: list[Image.Image], retries: int = 5) -> Optional[dict]:
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY not found")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)

    for attempt in range(retries):
        try:
            log_info(f"Gemini Vision attempt {attempt + 1}")
            
            # Pass the prompt and ALL images directly to Gemini
            content = [EXTRACTION_PROMPT] + images
            response = model.generate_content(content)
            raw_response = response.text.strip() if response.text else ""
            log_info(f"Gemini Response: {raw_response[:300]}")
            
            return parse_json_response(raw_response)
        except Exception as e:
            error_msg = str(e)
            log_error(f"Gemini attempt failed: {error_msg}")
            if attempt < retries - 1:
                # If it's a rate limit error (429), we need to wait much longer
                if "429" in error_msg or "Quota exceeded" in error_msg:
                    sleep_time = 30 + (attempt * 10) # 30s, 40s, 50s
                    log_warning(f"Rate limit hit! Sleeping for {sleep_time} seconds before retrying...")
                    time.sleep(sleep_time)
                else:
                    time.sleep(4)
            else:
                raise

    return None


# ==========================================================
# MAIN FUNCTION
# ==========================================================

def extract_invoice_data(file_path: str) -> dict:
    file_path = str(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    extension = Path(file_path).suffix.lower()
    log_info(f"Processing invoice: {file_path}")

    if extension == ".pdf":
        images = pdf_to_images(file_path)
    elif extension in [".png", ".jpg", ".jpeg", ".webp"]:
        images = [load_image(file_path)]
    else:
        raise ValueError(f"Unsupported file type: {extension}")

    # Process using Gemini Vision directly
    extracted_data = extract_from_images(images)

    if extracted_data is None:
        raise RuntimeError("Invoice extraction failed")

    log_info(f"Final Data: {extracted_data}")
    return extracted_data


# ==========================================================
# MODEL TEST
# ==========================================================

def test_gemini():
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content("Say Hello")
    print(response.text)

if __name__ == "__main__":
    test_gemini()
