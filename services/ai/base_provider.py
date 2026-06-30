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
STEP 1 - Detect Sections: Mentally divide the document into Header, Footer, Items, and Summary.
STEP 2 - Extract Summary First: Search the ENTIRE document (including headers/footers) for summary fields: Subtotal, Tax (GST/VAT/TCS), Shipping/Freight, Handling, Packing, Insurance, Discounts, Round Off, and Grand Total. Extract these EXACTLY as printed. Do not calculate anything.
STEP 3 - Extract Products: Now extract the line items. Ignore the summary section.

Field Mappings:
- invoice_number: The unique identifier for the invoice.
- vendor_name: The company who issued the invoice.
- invoice_date: The date the invoice was issued (DD-MM-YYYY).
- gst_number: The GSTIN or tax identification number.
- subtotal: The amount before taxes and discounts.
- tax_amount: Includes GST, CGST, SGST, IGST, VAT, Sales Tax.
- discount_amount: Includes Discount, Coupon Discount.
- shipping_charges: Includes Shipping, Freight, Delivery.
- packing_charges: Includes Packing, Packaging.
- handling_charges: Includes Handling.
- insurance_charges: Includes Insurance.
- other_charges: Includes Service Charges, Misc Charges, Convenience Fee, Fuel Surcharge, Loading/Unloading, TCS, TDS.
- round_off: Any rounding adjustment amount.
- total_amount: The printed Grand Total / Invoice Total.
- extraction_logs: For EVERY miscellaneous charge or tax found outside the item table, generate a log string. Format: "[Charge Type]: [Page Number] -> [Section Name] -> [Value]".
- line_items: Extract Description, Quantity, Unit Price, and Line Total for each product.

CRITICAL OCR RULES:
- DEEP SCAN REQUIRED: You must scan the ENTIRE invoice. Do not stop at the item table. Search the Header, Footer, Summary section, Totals section, margins, and the last page for any of the charges listed above.
- IGNORE NON-FINANCIAL NUMBERS: Do NOT extract Product IDs, SKU numbers, Part numbers, Item codes, Phone numbers, Serial numbers, PIN codes, ZIP codes, or PO numbers as monetary values.
- DETECT MONEY CORRECTLY: Only extract a number as a monetary field if it is explicitly associated with a currency symbol, an amount column, or labeled as Total/Subtotal/Tax.
- NEVER perform math to guess missing values. Search the entire invoice (headers, footers, summary sections) for these fields.
- DO NOT strip commas or decimal points if present in the raw text.
- Return exactly what you see. If a field is missing or not explicitly a monetary value, return null.

INVOICE TEXT:
"""

RECOVERY_PROMPT = """
You are an invoice extraction expert performing a RECOVERY PASS.
Our mathematical engine detected a massive discrepancy in your initial extraction.

The Printed Grand Total you extracted is: {printed_total}
But the sum of the Line Items and existing charges evaluates to: {calculated_total}
We are missing exactly: {gap}

Your sole job is to scour the ENTIRE document (specifically the Summary, Footer, and Header sections) looking for ANY missing charges (Shipping, Freight, Handling, Insurance, Tax, Round Off, TCS, TDS, etc.) that bridge this exact gap of {gap}.

Required JSON format:
{{
  "shipping_charges": float,
  "packing_charges": float,
  "handling_charges": float,
  "insurance_charges": float,
  "tax_amount": float,
  "discount_amount": float,
  "other_charges": float,
  "round_off": float,
  "extraction_logs": [
    "string"
  ]
}}

If you find a charge that matches (or partially matches) the missing gap, return it in the correct field. If a field is not found, return null. 
Do NOT return line items. Focus ONLY on summary charges.
Do NOT return markdown formatting (no ```json).

INVOICE TEXT:
"""

class BaseProvider(ABC):
    @abstractmethod
    def extract_invoice(self, invoice_text: str) -> dict:
        pass

    @abstractmethod
    def recover_invoice(self, invoice_text: str, printed_total: float, calculated_total: float, gap: float) -> dict:
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
