import json
import re
from abc import ABC, abstractmethod

EXTRACTION_PROMPT = """
You are an invoice extraction expert.
Please carefully read the provided invoice text and extract the following fields in valid JSON format.
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
4. gst_number: The GSTIN or tax identification number. If it is not present, return a blank string "".
5. subtotal: The amount before taxes. Do not include currency symbols, just the number. 
6. tax_amount: The total tax applied (GST/VAT). Do not include currency symbols. If multiple taxes exist, sum them up.
7. total_amount: The final total amount to be paid. Do not include currency symbols. 
8. line_items: Extract all individual items purchased or billed on the invoice. Include the description, quantity, price per unit, and the total line price.

CRITICAL MATH VERIFICATION:
- Double-check your numbers. The `subtotal` + `tax_amount` MUST mathematically equal the `total_amount`.
- If the OCR text is messy, use logic to deduce the correct amounts (e.g., if tax is 10%, subtotal is 100, then total must be 110).
- For each line item, `quantity` * `unit_price` MUST equal the line `total`.
- The sum of all line item `total`s MUST equal the `subtotal`. Fix any OCR typos that violate this math.

INVOICE TEXT:
"""

class BaseProvider(ABC):
    @abstractmethod
    def extract_invoice(self, invoice_text: str) -> dict:
        pass

    def parse_json_response(self, text: str) -> dict:
        if not text:
            raise ValueError("Model returned empty response")
        
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
            raise ValueError(f"Invalid JSON returned from model:\n{text[:500]}")
