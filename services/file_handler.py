import os
import shutil
from pathlib import Path
from typing import List
from config.db_config import INVOICES_DIR, PROCESSED_DIR, FAILED_DIR, SUPPORTED_FORMATS
from services.logger import log_info, log_warning


def ensure_dirs():
    for d in [INVOICES_DIR, PROCESSED_DIR, FAILED_DIR]:
        os.makedirs(d, exist_ok=True)


def scan_invoices() -> List[str]:
    """Return list of full file paths from the invoices folder."""
    ensure_dirs()
    files = []
    for f in sorted(Path(INVOICES_DIR).iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS:
            files.append(str(f))
        elif f.is_file():
            log_warning(f"Skipping unsupported file: {f.name}")
    log_info(f"Found {len(files)} invoice file(s) to process.")
    return files


def move_to_processed(file_path: str):
    dest = os.path.join(PROCESSED_DIR, Path(file_path).name)
    shutil.move(file_path, dest)
    log_info(f"Moved to processed: {dest}")


def move_to_failed(file_path: str):
    dest = os.path.join(FAILED_DIR, Path(file_path).name)
    shutil.move(file_path, dest)
    log_info(f"Moved to failed: {dest}")
