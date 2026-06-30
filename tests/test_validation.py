import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from services.parser import parse_invoice, _normalize_ocr_amount

def test_normalization():
    print("Testing OCR Normalization...")
    assert _normalize_ocr_amount("1,000.50") == 1000.50, "Failed to parse US thousands separator"
    assert _normalize_ocr_amount("1.000,50") == 1000.50, "Failed to parse EU thousands separator"
    assert _normalize_ocr_amount("10O.OO") == 100.0, "Failed to replace O with 0"
    assert _normalize_ocr_amount("l00.00") == 100.0, "Failed to replace l with 1"
    assert _normalize_ocr_amount("-50") is None, "Failed to reject negative numbers"
    assert _normalize_ocr_amount("₹ 20,000") == 20000.0, "Failed to strip currency symbol"
    print("✓ Normalization passed")

def test_arithmetic_engine():
    print("\nTesting Arithmetic Engine...")
    
    # Simulating a hallucinated LLM response based on messy OCR
    malformed_raw_data = {
        "invoice_number": "INV-001",
        "subtotal": 10000.0,  # Hallucinated wrong subtotal
        "tax_amount": 500.0,
        "discount_amount": "l00,00", # OCR typo: l instead of 1, comma instead of dot
        "total_amount": 99999.0, # Completely wrong total
        "line_items": [
            {
                "description": "Item 1",
                "quantity": "O.5", # Typos
                "unit_price": "l,000.00",
                "total": "50000" # OCR read extra zeros
            },
            {
                "description": "Item 2",
                "quantity": 2,
                "unit_price": 200.0,
                "total": 400.0 # Correctly OCR'd
            }
        ]
    }

    invoice = parse_invoice(malformed_raw_data, "test.pdf")
    
    # Verify Item 1 Math: 0.5 * 1000 = 500
    assert invoice.line_items[0]["total"] == 500.0, f"Expected 500.0, got {invoice.line_items[0]['total']}"
    
    # Verify Item 2 Math: 2 * 200 = 400
    assert invoice.line_items[1]["total"] == 400.0
    
    # Verify Subtotal: 500 + 400 = 900
    assert invoice.subtotal == 900.0, f"Expected 900.0, got {invoice.subtotal}"
    
    # Verify Discount parsed correctly: "l00,00" -> 100.00
    assert invoice.discount_amount == 100.0
    
    # Verify Tax
    assert invoice.tax_amount == 500.0
    
    # Verify Grand Total: Subtotal (900) + Tax (500) - Discount (100) = 1300
    assert invoice.total_amount == 1300.0, f"Expected 1300.0, got {invoice.total_amount}"
    
    # Verify validation logs
    assert len(invoice.validation_logs) > 0
    print("Validation Logs generated:")
    for log in invoice.validation_logs:
        print(f"  - {log}")
        
    print("✓ Arithmetic Engine passed")

if __name__ == "__main__":
    test_normalization()
    test_arithmetic_engine()
    print("\nAll Tests Passed Successfully! 🚀")
