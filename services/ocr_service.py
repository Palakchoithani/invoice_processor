
import os
import io
import json
import re
import time
import numpy as np
import easyocr

from pathlib import Path
from typing import Optional

from google import genai
from pdf2image import convert_from_path
from PIL import Image

from services.logger import log_info, log_error


# ==========================================================
# CONFIG
# ==========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = "gemini-2.5-flash"

log_info("Loading EasyOCR model...")
reader = easyocr.Reader(["en"])


EXTRACTION_PROMPT = """
You are an invoice extraction expert.

Convert the OCR text into the following JSON structure.

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


def pdf_to_image(file_path: str) -> Image.Image:
    pages = convert_from_path(file_path, dpi=200)

    if not pages:
        raise ValueError("PDF contains no pages")

    return pages[0]


# ==========================================================
# OCR
# ==========================================================

def extract_text_with_easyocr(image: Image.Image) -> str:
    """
    Extract raw text using EasyOCR.
    """

    image_np = np.array(image)

    results = reader.readtext(
        image_np,
        detail=0
    )

    text = "\n".join(results)

    if not text.strip():
        raise ValueError(
            "No text extracted from invoice"
        )

    return text


# ==========================================================
# JSON PARSER
# ==========================================================

def parse_json_response(text: str) -> dict:

    if not text:
        raise ValueError(
            "Gemini returned empty response"
        )

    text = text.strip()

    text = re.sub(
        r"^```json",
        "",
        text
    )

    text = re.sub(
        r"^```",
        "",
        text
    )

    text = re.sub(
        r"```$",
        "",
        text
    )

    try:
        return json.loads(text)

    except Exception:

        match = re.search(
            r"\{.*\}",
            text,
            re.DOTALL
        )

        if match:
            return json.loads(
                match.group()
            )

        raise ValueError(
            f"Invalid Gemini JSON:\n{text[:500]}"
        )


# ==========================================================
# GEMINI STRUCTURING
# ==========================================================

def structure_invoice_data(
    ocr_text: str,
    retries: int = 3
) -> Optional[dict]:

    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY not found"
        )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = f"""
{EXTRACTION_PROMPT}

OCR TEXT:

{ocr_text}
"""

    for attempt in range(retries):

        try:

            log_info(
                f"Gemini attempt {attempt + 1}"
            )

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )

            raw_response = (
                response.text.strip()
                if response.text
                else ""
            )

            log_info(
                f"Gemini Response: {raw_response[:300]}"
            )

            return parse_json_response(
                raw_response
            )

        except Exception as e:

            log_error(
                f"Gemini attempt failed: {str(e)}"
            )

            if attempt < retries - 1:
                time.sleep(2)

            else:
                raise

    return None


# ==========================================================
# MAIN FUNCTION
# ==========================================================

def extract_invoice_data(
    file_path: str
) -> dict:

    file_path = str(file_path)

    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    extension = (
        Path(file_path)
        .suffix
        .lower()
    )

    log_info(
        f"Processing invoice: {file_path}"
    )

    if extension == ".pdf":

        image = pdf_to_image(
            file_path
        )

    elif extension in [
        ".png",
        ".jpg",
        ".jpeg",
        ".webp"
    ]:

        image = load_image(
            file_path
        )

    else:

        raise ValueError(
            f"Unsupported file type: {extension}"
        )

    # STEP 1
    ocr_text = extract_text_with_easyocr(
        image
    )

    log_info(
        f"OCR extracted {len(ocr_text)} characters"
    )

    # STEP 2
    extracted_data = structure_invoice_data(
        ocr_text
    )

    if extracted_data is None:

        raise RuntimeError(
            "Invoice extraction failed"
        )

    log_info(
        f"Final Data: {extracted_data}"
    )

    return extracted_data


# ==========================================================
# MODEL TEST
# ==========================================================

def test_gemini():

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="Say Hello"
    )

    print(response.text)


if __name__ == "__main__":
    test_gemini()

