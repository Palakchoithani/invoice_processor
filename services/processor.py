import time
from pathlib import Path
from datetime import datetime

from services.ocr_service import extract_invoice_data
from services.parser import parse_invoice
from services.validator import validate_invoice
from services.database import (
    save_invoice,
    get_job_by_hash,
    create_or_update_job
)

from services.duplicate_detector import (
    run_duplicate_checks,
    generate_ocr_fingerprint
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
    file_size = Path(file_path).stat().st_size
    file_hash = calculate_file_hash(file_path)

    log_info(f"[Upload Completed] Starting processing pipeline for file: {file_name} (hash={file_hash})")

    # 2. Set to PROCESSING - OCR Stage
    log_info(f"[Firebase Write] Creating document job for {file_name}")
    create_or_update_job(DocumentJob(
        file_hash=file_hash,
        file_name=file_name,
        status="PROCESSING",
        stage="OCR",
        progress=10,
        file_size=file_size
    ))
    processing_path = move_to_processing(file_path)

    def fail_job(msg: str, progress: int = 0):
        log_error(f"[Pipeline Failed] File: {file_name}, error: {msg}")
        create_or_update_job(DocumentJob(
            file_hash=file_hash,
            file_name=file_name,
            status="FAILED",
            stage="FAILED",
            progress=progress,
            error_message=msg
        ))
        move_to_failed(processing_path)
        return {"file": file_name, "status": "FAILED", "detail": msg}

    # 3. Extract invoice data (OCR)
    log_info(f"[OCR Started] Performing OCR data extraction on: {file_name}")
    try:
        raw_data, invoice_text = extract_invoice_data(processing_path)
        log_info(f"[OCR Completed] Successfully extracted text fingerprint from: {file_name}")
    except Exception as e:
        import traceback
        log_error(f"OCR Exception stack trace:\n{traceback.format_exc()}")
        return fail_job(f"Extraction failed: {e}", 20)

    # Transition to AI
    create_or_update_job(DocumentJob(
        file_hash=file_hash,
        file_name=file_name,
        status="PROCESSING",
        stage="AI",
        progress=40
    ))

    # 4. Parse invoice (AI) & Handle Mismatch Recovery
    log_info(f"[AI Started] Analyzing extraction schema using Generative AI model for: {file_name}")
    try:
        from services.parser import MismatchException
        from services.ocr_service import ai_router
        try:
            invoice = parse_invoice(raw_data, file_name)
        except MismatchException as mismatch:
            log_warning(f"[Math Mismatch] Math Mismatch Detected: {mismatch}. Triggering OCR Recovery Pass...")
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
        log_info(f"[AI Completed] AI parse finished for: {file_name}")

    except Exception as e:
        import traceback
        log_error(f"AI Exception stack trace:\n{traceback.format_exc()}")
        return fail_job(f"Parsing failed: {e}", 50)

    # Transition to VALIDATION
    create_or_update_job(DocumentJob(
        file_hash=file_hash,
        file_name=file_name,
        status="PROCESSING",
        stage="VALIDATION",
        progress=70
    ))

    # 5. Validate invoice
    log_info(f"[Validation Started] Running math integrity rules validation for: {file_name}")
    valid, reason = validate_invoice(invoice)
    if not valid:
        return fail_job(reason, 75)
    log_info(f"[Validation Completed] Integrity checks passed for: {file_name}")

    # 6. Advanced Duplicate Checks (Levels 2-4)
    log_info(f"[Duplicate Check] Running metadata and OCR fingerprint duplicate tests for: {file_name}")
    invoice.file_hash = file_hash
    invoice.ocr_fingerprint = generate_ocr_fingerprint(invoice_text)
    
    is_dup, level, reason = run_duplicate_checks(
        file_hash=None, # Already checked Level 1 in API controller
        invoice_number=invoice.invoice_number,
        vendor_name=invoice.vendor_name,
        invoice_date=invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        total_amount=invoice.total_amount,
        line_items_count=len(invoice.line_items) if invoice.line_items else 0,
        ocr_fingerprint=invoice.ocr_fingerprint
    )
    
    if is_dup:
        log_warning(f"[Duplicate Check] Duplicate identified at {level}: {reason}")
        create_or_update_job(DocumentJob(
            file_hash=file_hash,
            file_name=file_name,
            status="DUPLICATE",
            stage="DUPLICATE",
            progress=100,
            error_message=reason,
            invoice_number=invoice.invoice_number,
            vendor_name=invoice.vendor_name,
            invoice_date=invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            total_amount=invoice.total_amount
        ))
        move_to_processed(processing_path)
        log_info(f"[Processing Completed] Duplicate resolved. No database save for: {file_name}")
        return {
            "file": file_name,
            "status": "DUPLICATE",
            "detail": reason,
        }

    # Transition to SAVING
    create_or_update_job(DocumentJob(
        file_hash=file_hash,
        file_name=file_name,
        status="PROCESSING",
        stage="SAVING",
        progress=90
    ))

    # 7. Save invoice
    log_info(f"[Firebase Write] Saving extracted invoice object: {invoice.invoice_number}")
    try:
        firestore_id = save_invoice(invoice)
        create_or_update_job(DocumentJob(
            file_hash=file_hash,
            file_name=file_name,
            status="PROCESSED",
            stage="COMPLETED",
            progress=100,
            invoice_id=firestore_id,
            invoice_number=invoice.invoice_number,
            vendor_name=invoice.vendor_name,
            invoice_date=invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            total_amount=invoice.total_amount,
            processing_time=invoice.processing_time.isoformat() if invoice.processing_time else datetime.now().isoformat()
        ))
        move_to_processed(processing_path)
        log_info(f"[Firebase Write] Invoice saved. Firestore ID={firestore_id}")
        log_info(f"[Processing Completed] Successfully finalized invoice extraction for: {file_name}")

        return {
            "file": file_name,
            "status": "SUCCESS",
            "detail": "Invoice saved successfully",
            "firestore_id": firestore_id,
            "invoice": invoice.to_dict(),
        }
    except Exception as e:
        import traceback
        log_error(f"Saving Exception stack trace:\n{traceback.format_exc()}")
        return fail_job(f"Save failed: {e}", 95)

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

