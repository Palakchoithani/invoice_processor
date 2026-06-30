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
  "extraction_logs": [
    "string"
  ],
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
7. tax_amount: The total tax applied. Includes: GST, CGST, SGST, IGST, VAT, Sales Tax. If multiple taxes exist, sum them up.
8. discount_amount: The total discount applied. Includes: Discount, Coupon Discount.
9. shipping_charges: Includes: Shipping, Freight, Delivery, Transportation.
10. packing_charges: Includes: Packing, Packaging.
11. handling_charges: Includes: Handling.
12. insurance_charges: Includes: Insurance.
13. other_charges: Includes: Service Charges, Miscellaneous Charges, Other Charges, Convenience Fee, Fuel Surcharge, Loading/Unloading Charges, TCS, TDS.
14. round_off: Any rounding adjustment amount (could be negative or positive).
15. total_amount: The final total amount to be paid (usually labeled Grand Total, Invoice Total).
16. extraction_logs: For EVERY charge found outside the main line-items table (Shipping, Taxes, Discounts, Handling, etc.), you MUST create a log string stating exactly where you found it. Format: "[Charge Type]: [Page Number] -> [Section Name] -> [Value]". Example: "Shipping: Page 1 -> Summary Section -> 5000", "GST: Page 2 -> Footer -> 38114.60".
17. line_items: Extract all individual items purchased or billed on the invoice. Include the description, quantity, price per unit, and the total line price.

CRITICAL OCR RULES:
- DEEP SCAN REQUIRED: You must scan the ENTIRE invoice. Do not stop at the item table. Search the Header, Footer, Summary section, Totals section, margins, and the last page for any of the charges listed above.
- IGNORE NON-FINANCIAL NUMBERS: Do NOT extract Product IDs, SKU numbers, Part numbers, Item codes, Phone numbers, Serial numbers, PIN codes, ZIP codes, or PO numbers as monetary values.
- DETECT MONEY CORRECTLY: Only extract a number as a monetary field if it is explicitly associated with a currency symbol, an amount column, or labeled as Total/Subtotal/Tax.
- NEVER perform math to guess missing values. Search the entire invoice (headers, footers, summary sections) for these fields.
- DO NOT strip commas or decimal points if present in the raw text.
- Return exactly what you see. If a field is missing or not explicitly a monetary value, return null.

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
