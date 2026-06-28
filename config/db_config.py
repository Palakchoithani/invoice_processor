import os
from dotenv import load_dotenv

load_dotenv()

FIREBASE_KEY_PATH = os.getenv("FIREBASE_KEY_PATH", "firebase-key.json")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

INVOICES_DIR = "invoices"
PROCESSED_DIR = "processed"
FAILED_DIR = "failed"
LOGS_DIR = "logs"

SUPPORTED_FORMATS = {".pdf", ".jpg", ".jpeg", ".png"}
