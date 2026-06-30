import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from services.ai.ai_router import AIRouter
from services.ai.base_provider import BaseProvider
from services.logger import log_info

class MockProvider(BaseProvider):
    def __init__(self):
        self.attempts = 0
    def extract_invoice(self, invoice_text: str) -> dict:
        self.attempts += 1
        log_info(f"Attempt {self.attempts}")
        if self.attempts < 3:
            raise Exception(f"Simulated API failure {self.attempts}")
        return {"status": "success"}

router = AIRouter()
router.providers = {"mock": MockProvider()}
router.priority = ["mock"]

print("Starting extraction...")
result = router.route_extraction("test")
print("Final Result:", result)
