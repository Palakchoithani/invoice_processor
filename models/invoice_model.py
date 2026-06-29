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
    total_amount: Optional[float] = None
    file_name: Optional[str] = None
    line_items: Optional[List[Dict[str, Any]]] = field(default_factory=list)
    processing_time: Optional[datetime] = None

    def to_dict(self):
        return {
            "invoice_number": self.invoice_number,
            "vendor_name": self.vendor_name,
            "invoice_date": str(self.invoice_date) if self.invoice_date else None,
            "gst_number": self.gst_number,
            "subtotal": self.subtotal,
            "tax_amount": self.tax_amount,
            "total_amount": self.total_amount,
            "file_name": self.file_name,
            "line_items": self.line_items,
            "processing_time": str(self.processing_time) if self.processing_time else None,
        }


@dataclass
class ProcessingLog:
    file_name: str
    status: str  # SUCCESS | FAILED | DUPLICATE | SKIPPED
    error_message: Optional[str] = None
