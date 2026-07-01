import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).parent))
load_dotenv()

from services.ai.ai_router import AIRouter
from services.logger import log_info

router = AIRouter()

sample_invoice_text = """
Invoice #INV-2023-001
Vendor: Example Corp
Date: 2023-10-25
GSTIN: 22AAAAA0000A1Z5

Description         Qty     Price       Total
Laptop              1       1000.00     1000.00
Mouse               2       50.00       100.00

Subtotal: 1100.00
Tax (10%): 110.00
Total: 1210.00
"""

print("Testing AI Router with real API keys...")
try:
    result = router.extract_with_consensus(sample_invoice_text, "test.pdf")
    print("SUCCESS! Extraction Result:")
    print(result)
except Exception as e:
    print(f"FAILED! Error: {e}")
