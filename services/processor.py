
import time
from pathlib import Path

from services.ocr_service import extract_invoice_data
from services.parser import parse_invoice
from services.validator import validate_invoice
from services.database import (
    check_duplicate,
    save_invoice,
    write_log,
)
from services.firebase_service import save_invoice as save_to_firestore

from services.file_handler import (
    move_to_processed,
    move_to_failed,
)

from services.logger import (
    log_info,
    log_error,
    log_warning,
)

from models.invoice_model import ProcessingLog


def process_single_invoice(file_path: str) -> dict:
    """
    Complete processing pipeline for a single invoice.
    """

    file_name = Path(file_path).name

    log_info(f"Processing invoice: {file_name}")

    # --------------------------------------------------
    # 1. Extract invoice data
    # --------------------------------------------------
    try:
        raw_data = extract_invoice_data(file_path)

    except Exception as e:

        msg = f"Extraction failed: {e}"

        log_error(msg)

        write_log(
            ProcessingLog(
                file_name=file_name,
                status="FAILED",
                error_message=msg,
            )
        )

        move_to_failed(file_path)

        return {
            "file": file_name,
            "status": "FAILED",
            "detail": msg,
        }

    # --------------------------------------------------
    # 2. Parse invoice
    # --------------------------------------------------
    try:

        invoice = parse_invoice(
            raw_data,
            file_name,
        )

    except Exception as e:

        msg = f"Parsing failed: {e}"

        log_error(msg)

        write_log(
            ProcessingLog(
                file_name=file_name,
                status="FAILED",
                error_message=msg,
            )
        )

        move_to_failed(file_path)

        return {
            "file": file_name,
            "status": "FAILED",
            "detail": msg,
        }

    # --------------------------------------------------
    # 3. Validate invoice
    # --------------------------------------------------
    valid, reason = validate_invoice(invoice)

    if not valid:

        log_warning(
            f"Validation failed for {file_name}: {reason}"
        )

        write_log(
            ProcessingLog(
                file_name=file_name,
                status="FAILED",
                error_message=reason,
            )
        )

        move_to_failed(file_path)

        return {
            "file": file_name,
            "status": "FAILED",
            "detail": reason,
        }

    # --------------------------------------------------
    # 4. Duplicate check
    # --------------------------------------------------
    if check_duplicate(invoice.invoice_number):

        msg = (
            f"Duplicate invoice number: "
            f"{invoice.invoice_number}"
        )

        log_warning(msg)

        write_log(
            ProcessingLog(
                file_name=file_name,
                status="DUPLICATE",
                error_message=msg,
            )
        )

        move_to_processed(file_path)

        return {
            "file": file_name,
            "status": "DUPLICATE",
            "detail": msg,
        }

    # --------------------------------------------------
    # 5. Save invoice
    # --------------------------------------------------
    try:

        # Existing SQL / Local DB
        row_id = save_invoice(invoice)

        # Firestore
        firestore_id = save_to_firestore(
            invoice.to_dict()
        )

        write_log(
            ProcessingLog(
                file_name=file_name,
                status="SUCCESS",
            )
        )

        move_to_processed(file_path)

        log_info(
            f"Invoice saved. "
            f"DB ID={row_id}, "
            f"Firestore ID={firestore_id}"
        )

        return {
            "file": file_name,
            "status": "SUCCESS",
            "detail": "Invoice saved successfully",
            "database_id": row_id,
            "firestore_id": firestore_id,
            "invoice": invoice.to_dict(),
        }

    except Exception as e:

        msg = f"Save failed: {e}"

        log_error(msg)

        write_log(
            ProcessingLog(
                file_name=file_name,
                status="FAILED",
                error_message=msg,
            )
        )

        move_to_failed(file_path)

        return {
            "file": file_name,
            "status": "FAILED",
            "detail": msg,
        }


def process_all_invoices() -> list[dict]:

    from services.file_handler import scan_invoices

    files = scan_invoices()

    if not files:

        log_info("No invoice files found.")

        return []

    results = []

    total_files = len(files)

    for index, file_path in enumerate(files):

        result = process_single_invoice(
            file_path
        )

        results.append(result)

        if index < total_files - 1:

            delay_seconds = 4

            log_info(
                f"Waiting {delay_seconds}s "
                f"before next invoice..."
            )

            time.sleep(delay_seconds)

    log_info(
        f"Completed processing "
        f"{len(results)} invoice(s)"
    )

    return results

