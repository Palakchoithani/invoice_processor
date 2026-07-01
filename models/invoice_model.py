from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import date, datetime


@dataclass
class Invoice:
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    invoice_date: Optional[date] = None
    gst_number: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    shipping_charges: Optional[float] = None
    packing_charges: Optional[float] = None
    handling_charges: Optional[float] = None
    insurance_charges: Optional[float] = None
    other_charges: Optional[float] = None
    round_off: Optional[float] = None
    total_amount: Optional[float] = None
    file_name: Optional[str] = None
    file_hash: Optional[str] = None
    ocr_fingerprint: Optional[str] = None
    line_items: Optional[List[Dict[str, Any]]] = field(default_factory=list)
    confidence_score: float = 1.0
    validation_logs: List[str] = field(default_factory=list)
    extraction_logs: List[str] = field(default_factory=list)
    processing_time: Optional[datetime] = None

    def to_dict(self):
        return {
            "invoice_number": self.invoice_number,
            "vendor_name": self.vendor_name,
            "invoice_date": self.invoice_date.strftime("%d-%m-%Y") if self.invoice_date else None,
            "gst_number": self.gst_number,
            "subtotal": self.subtotal,
            "tax_amount": self.tax_amount,
            "discount_amount": self.discount_amount,
            "shipping_charges": self.shipping_charges,
            "packing_charges": self.packing_charges,
            "handling_charges": self.handling_charges,
            "insurance_charges": self.insurance_charges,
            "other_charges": self.other_charges,
            "round_off": self.round_off,
            "total_amount": self.total_amount,
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "ocr_fingerprint": self.ocr_fingerprint,
            "line_items": self.line_items,
            "confidence_score": self.confidence_score,
            "validation_logs": self.validation_logs,
            "extraction_logs": self.extraction_logs,
            "processing_time": str(self.processing_time) if self.processing_time else None,
        }


@dataclass
class ProcessingLog:
    file_name: str
    status: str  # SUCCESS | FAILED | DUPLICATE | SKIPPED
    error_message: Optional[str] = None


@dataclass
class DocumentJob:
    file_hash: str
    file_name: str
    status: str  # PENDING | QUEUED | PROCESSING | PROCESSED | FAILED | DUPLICATE
    progress: int = 0
    stage: str = "PENDING"
    file_size: Optional[int] = 0
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    invoice_date: Optional[str] = None
    total_amount: Optional[float] = None
    processing_time: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self):
        return {
            "file_hash": self.file_hash,
            "file_name": self.file_name,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "file_size": self.file_size,
            "invoice_id": self.invoice_id,
            "invoice_number": self.invoice_number,
            "vendor_name": self.vendor_name,
            "invoice_date": self.invoice_date,
            "total_amount": self.total_amount,
            "processing_time": self.processing_time,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else datetime.now().isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else datetime.now().isoformat(),
        }
