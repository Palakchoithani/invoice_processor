import os
import shutil
import hashlib
from pathlib import Path
from typing import List
from config.db_config import PENDING_DIR, PROCESSING_DIR, PROCESSED_DIR, FAILED_DIR, SUPPORTED_FORMATS
from services.logger import log_info, log_warning


def ensure_dirs():
    for d in [PENDING_DIR, PROCESSING_DIR, PROCESSED_DIR, FAILED_DIR]:
        os.makedirs(d, exist_ok=True)


def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def scan_pending_invoices() -> List[str]:
    """Return list of full file paths from the pending folder."""
    ensure_dirs()
    files = []
    for f in sorted(Path(PENDING_DIR).iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS:
            files.append(str(f))
        elif f.is_file():
            log_warning(f"Skipping unsupported file: {f.name}")
    log_info(f"Found {len(files)} invoice file(s) in pending.")
    return files


def move_file(file_path: str, target_dir: str) -> str:
    """Move file to target directory and return new path."""
    dest = os.path.join(target_dir, Path(file_path).name)
    shutil.move(file_path, dest)
    return dest


def move_to_processing(file_path: str) -> str:
    dest = move_file(file_path, PROCESSING_DIR)
    log_info(f"Moved to processing: {dest}")
    return dest


def move_to_processed(file_path: str) -> str:
    dest = move_file(file_path, PROCESSED_DIR)
    log_info(f"Moved to processed: {dest}")
    return dest


def move_to_failed(file_path: str) -> str:
    dest = move_file(file_path, FAILED_DIR)
    log_info(f"Moved to failed: {dest}")
    return dest
