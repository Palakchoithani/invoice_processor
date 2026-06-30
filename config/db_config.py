import os
from dotenv import load_dotenv

load_dotenv()

FIREBASE_KEY_PATH = os.getenv("FIREBASE_KEY_PATH", "firebase-key.json")

# Vercel Serverless compatibility: use /tmp
BASE_DIR = os.getenv("TMPDIR", "/tmp")

INVOICES_DIR = os.path.join(BASE_DIR, "invoices")
FAILED_DIR = os.path.join(BASE_DIR, "failed")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

LOGS_DIR = "logs"

SUPPORTED_FORMATS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
