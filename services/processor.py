import time
from pathlib import Path
from datetime import datetime

from services.ocr_service import extract_invoice_data
from services.parser import parse_invoice
from services.validator import validate_invoice
from services.database import (
    check_duplicate,
    save_invoice,
    get_job_by_hash,
    create_or_update_job
)

from services.file_handler import (
    move_to_processed,
    move_to_failed,
    move_to_processing,
    calculate_file_hash
)

from services.logger import (
    log_info,
    log_error,
    log_warning,
)

from models.invoice_model import DocumentJob


def process_single_invoice(file_path: str) -> dict:
    """
    Complete processing pipeline for a single invoice.
    """
    if not Path(file_path).exists():
        return {"status": "FAILED", "detail": "File not found"}

    file_name = Path(file_path).name
    file_hash = calculate_file_hash(file_path)

    # 1. Hash Duplicate Prevention
    existing_job = get_job_by_hash(file_hash)
    if existing_job and existing_job.get("status") == "PROCESSED":
        msg = "Duplicate file upload (hash matched)."
        log_warning(f"{msg} File: {file_name}")
        return {
            "file": file_name,
            "status": "DUPLICATE",
            "detail": msg,
        }

    # 2. Set to PROCESSING
    create_or_update_job(DocumentJob(
        file_hash=file_hash,
        file_name=file_name,
        status="PROCESSING"
    ))
    processing_path = move_to_processing(file_path)

    log_info(f"Processing invoice: {file_name}")

    def fail_job(msg: str):
        log_error(msg)
        create_or_update_job(DocumentJob(
            file_hash=file_hash,
            file_name=file_name,
            status="FAILED",
            error_message=msg
        ))
        move_to_failed(processing_path)
        return {"file": file_name, "status": "FAILED", "detail": msg}

    # 3. Extract invoice data
    try:
        raw_data, invoice_text = extract_invoice_data(processing_path)
    except Exception as e:
        return fail_job(f"Extraction failed: {e}")

    # 4. Parse invoice & Handle Mismatch Recovery
    try:
        from services.parser import MismatchException
        from services.ocr_service import ai_router
        try:
            invoice = parse_invoice(raw_data, file_name)
        except MismatchException as mismatch:
            log_warning(f"Math Mismatch Detected: {mismatch}. Triggering OCR Recovery Pass...")
            recovered_data = ai_router.recover_missing_charges(
                invoice_text=invoice_text,
                printed_total=mismatch.printed_total,
                calculated_total=mismatch.calculated_total,
                gap=mismatch.gap
            )
            for key in ["shipping_charges", "packing_charges", "handling_charges", "insurance_charges", "tax_amount", "discount_amount", "other_charges", "round_off"]:
                if recovered_data.get(key) is not None:
                    raw_data[key] = recovered_data[key]
            if "extraction_logs" in recovered_data and recovered_data["extraction_logs"]:
                if "extraction_logs" not in raw_data:
                    raw_data["extraction_logs"] = []
                raw_data["extraction_logs"].extend(recovered_data["extraction_logs"])
                
            invoice = parse_invoice(raw_data, file_name, recovery_pass=True)
            invoice.confidence_score = round(max(0.0, invoice.confidence_score - 0.20), 2)
            invoice.validation_logs.append("OCR Recovery Pass Successfully Bridged Gap")

    except Exception as e:
        return fail_job(f"Parsing failed: {e}")

    # 5. Validate invoice
    valid, reason = validate_invoice(invoice)
    if not valid:
        return fail_job(reason)

    # 6. Invoice Number Duplicate Check (Logical Duplicate)
    if check_duplicate(invoice.invoice_number):
        msg = f"Duplicate invoice number: {invoice.invoice_number}"
        log_warning(msg)
        create_or_update_job(DocumentJob(
            file_hash=file_hash,
            file_name=file_name,
            status="FAILED",  # Marking as FAILED so it's not double counted, but we'll show duplicate message
            error_message=msg
        ))
        move_to_failed(processing_path)
        return {
            "file": file_name,
            "status": "FAILED",
            "detail": msg,
        }

    # 7. Save invoice
    try:
        firestore_id = save_invoice(invoice)
        create_or_update_job(DocumentJob(
            file_hash=file_hash,
            file_name=file_name,
            status="PROCESSED",
            invoice_id=firestore_id,
            total_amount=invoice.total_amount
        ))
        move_to_processed(processing_path)
        log_info(f"Invoice saved. Firestore ID={firestore_id}")

        return {
            "file": file_name,
            "status": "SUCCESS",
            "detail": "Invoice saved successfully",
            "firestore_id": firestore_id,
            "invoice": invoice.to_dict(),
        }
    except Exception as e:
        return fail_job(f"Save failed: {e}")

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

