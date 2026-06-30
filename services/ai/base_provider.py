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
  "invoice_date": "DD-MM-YYYY",
  "gst_number": "string",
  "subtotal": float,
  "tax_amount": float,
  "discount_amount": float,
  "shipping_charges": float,
  "packing_charges": float,
  "handling_charges": float,
  "insurance_charges": float,
  "other_charges": float,
  "round_off": float,
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
1. Extract numbers EXACTLY as written on the document. Do not invent values or perform arithmetic.
2. invoice_number: The unique identifier for the invoice (e.g. invoice #, bill no). Look for slashes or dashes.
3. vendor_name: The company or person who issued the invoice. Usually at the top.
4. invoice_date: The date the invoice was issued, formatted as DD-MM-YYYY.
5. gst_number: The GSTIN or tax identification number. If it is not present, return a blank string "".
6. subtotal: The amount before taxes and discounts. Do not include currency symbols.
7. tax_amount: The total tax applied (GST/VAT). Do not include currency symbols. If multiple taxes exist, sum them up.
8. discount_amount: The total discount applied. Do not include currency symbols.
9. shipping_charges: Any charges for shipping, freight, delivery, or transportation.
10. packing_charges: Any charges for packing or packaging.
11. handling_charges: Any charges for handling or service fees.
12. insurance_charges: Any charges for insurance.
13. other_charges: Any miscellaneous or other charges.
14. round_off: Any rounding adjustment amount (could be negative or positive).
15. total_amount: The final total amount to be paid (usually labeled Grand Total, Invoice Total).
16. line_items: Extract all individual items purchased or billed on the invoice. Include the description, quantity, price per unit, and the total line price.

CRITICAL OCR RULES:
- NEVER perform math to guess missing values. Search the entire invoice (headers, footers, summary sections) for these fields.
- DO NOT strip commas or decimal points if present in the raw text.
- Return exactly what you see. If a field is missing, return null.

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
