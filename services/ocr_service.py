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
Please carefully read the provided invoice image(s) and extract the following fields in valid JSON format.
If a field is not found, return null for that field. Do NOT return markdown formatting (no ```json).

Required JSON format:
{
  "invoice_number": "string",
  "vendor_name": "string",
  "invoice_date": "YYYY-MM-DD",
  "gst_number": "string",
  "subtotal": float,
  "tax_amount": float,
  "total_amount": float,
  "line_items": [
    {
      "description": "string",
      "quantity": float,
      "unit_price": float,
      "total": float
    }
  ]
}

Instructions:
1. invoice_number: The unique identifier for the invoice (e.g. invoice #, bill no). Look for slashes or dashes.
2. vendor_name: The company or person who issued the invoice. Usually at the top.
3. invoice_date: The date the invoice was issued, formatted as YYYY-MM-DD.
4. gst_number: The GSTIN or tax identification number.
5. subtotal: The amount before taxes. Do not include currency symbols, just the number.
6. tax_amount: The total tax applied (GST/VAT). Do not include currency symbols.
7. total_amount: The final total amount to be paid. Do not include currency symbols.
8. line_items: Extract all individual items purchased or billed on the invoice. Include the description, quantity, price per unit, and the total line price.
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
            
            from google.generativeai.types import HarmCategory, HarmBlockThreshold
            
            # Disable safety filters as invoices often contain names/addresses that trigger false positives
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            
            # Pass the prompt and ALL images directly to Gemini
            content = [EXTRACTION_PROMPT] + images
            response = model.generate_content(content, safety_settings=safety_settings)
            
            try:
                raw_response = response.text.strip() if response.text else ""
            except Exception as text_err:
                # Fallback if response.text throws an exception due to safety blocks
                raw_response = ""
                if response.candidates and hasattr(response.candidates[0], "content") and response.candidates[0].content.parts:
                    raw_response = response.candidates[0].content.parts[0].text.strip()
                else:
                    log_warning(f"Gemini response blocked. Reason: {text_err}")
                    raise ValueError("Response blocked by safety filters.")
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
