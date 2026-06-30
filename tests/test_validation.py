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
    print("\nTesting Arithmetic Engine (Override)...")
    
    malformed_raw_data = {
        "invoice_number": "INV-001",
        "subtotal": 10000.0,
        "tax_amount": 500.0,
        "discount_amount": "l00,00",
        "shipping_charges": 50.0,
        "total_amount": 1351.0, # Small discrepancy that should be overridden silently
        "line_items": [
            {
                "description": "Item 1",
                "quantity": "O.5",
                "unit_price": "l,000.00",
                "total": "50000"
            },
            {
                "description": "Item 2",
                "quantity": 2,
                "unit_price": 200.0,
                "total": 400.0
            }
        ]
    }

    invoice = parse_invoice(malformed_raw_data, "test.pdf", recovery_pass=True)
    
    # Verify Math
    assert invoice.line_items[0]["total"] == 500.0
    assert invoice.line_items[1]["total"] == 400.0
    assert invoice.subtotal == 900.0
    assert invoice.discount_amount == 100.0
    assert invoice.shipping_charges == 50.0
    
    # Verify Grand Total: Subtotal (900) + Tax (500) - Discount (100) + Shipping (50) = 1350
    assert invoice.total_amount == 1350.0, f"Expected 1350.0, got {invoice.total_amount}"
    
    # Ensure it generated override logs
    assert any("Override" in log for log in invoice.validation_logs)
    print("✓ Arithmetic Engine (Override) passed")

def test_tolerance_and_charges():
    print("\nTesting Tolerance & Extra Charges (Acceptance)...")
    
    # Simulating a completely correct invoice that has floating point imprecision
    # and utilizes all 6 new charges
    perfect_raw_data = {
        "invoice_number": "INV-002",
        "subtotal": 100.0,
        "tax_amount": 5.0,
        "discount_amount": 10.0,
        "shipping_charges": 20.0,
        "packing_charges": 5.0,
        "handling_charges": 2.50,
        "insurance_charges": 10.0,
        "other_charges": 1.0,
        "round_off": -0.50,
        "total_amount": 133.0, # Math: 100 + 5 - 10 + (20 + 5 + 2.5 + 10 + 1) - 0.5 = 133.0
        "extraction_logs": [
            "Shipping: Page 1 -> Footer -> 20.0",
            "Packing: Page 1 -> Header -> 5.0"
        ],
        "line_items": [
            {
                "description": "Item 1",
                "quantity": 1,
                "unit_price": 100.0,
                "total": 100.0
            }
        ]
    }
    
    # Introduce floating point noise to OCR total (e.g. 133.004) -> it should still accept 133.004 because it's within 0.01 
    # Actually wait, let's say the printed total is 133.01, our math says 133.0. It should accept 133.01.
    perfect_raw_data["total_amount"] = 133.01
    
    invoice = parse_invoice(perfect_raw_data, "test2.pdf")
    
    # Verify it accepted the PRINTED total because difference is exactly 0.01
    assert invoice.total_amount == 133.01, f"Expected 133.01, got {invoice.total_amount}"
    assert any("Accepted" in log for log in invoice.validation_logs)
    assert len(invoice.extraction_logs) == 2, "Failed to parse extraction_logs"
    print("✓ Tolerance & Extra Charges & Extraction Logs passed")

def test_massive_hallucination():
    print("\nTesting Massive Hallucination Rejection...")
    malformed_raw_data = {
        "invoice_number": "INV-001",
        "subtotal": 1000.0,
        "total_amount": 344650.0, # Completely wrong total (Zip code hallucination)
        "line_items": [
            {
                "description": "Item 1",
                "quantity": 1,
                "unit_price": 1000.0,
                "total": 1000.0
            }
        ]
    }
    
    # Mathematical total is 1000. Printed total is 344650. Difference is 343650.
    # Threshold is 10% of 1000 = 100.
    # Difference (343650) > Threshold (100) -> Should raise ValueError
    try:
        parse_invoice(malformed_raw_data, "test.pdf", recovery_pass=True)
        assert False, "Should have raised ValueError for massive discrepancy"
    except ValueError as e:
        assert "Massive Discrepancy Detected" in str(e)
        print("✓ Massive Hallucination properly rejected")

if __name__ == "__main__":
    test_normalization()
    test_arithmetic_engine()
    test_tolerance_and_charges()
    test_massive_hallucination()
    print("\nAll Tests Passed Successfully! 🚀")
