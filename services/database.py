import mysql.connector
from mysql.connector import Error
from typing import Optional, List, Dict, Any
from datetime import datetime
from config.db_config import DB_CONFIG
from models.invoice_model import Invoice, ProcessingLog
from services.logger import log_info, log_error


def get_connection():
    """Create and return a MySQL connection."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        raise ConnectionError(f"Cannot connect to MySQL: {e}")


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                invoice_number VARCHAR(100) UNIQUE,
                vendor_name VARCHAR(255),
                invoice_date DATE,
                gst_number VARCHAR(30),
                subtotal DECIMAL(12,2),
                tax_amount DECIMAL(12,2),
                total_amount DECIMAL(12,2),
                file_name VARCHAR(255),
                processing_time DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                file_name VARCHAR(255),
                status VARCHAR(50),
                error_message TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        log_info("Database tables initialized.")
    finally:
        cursor.close()
        conn.close()


def check_duplicate(invoice_number: str) -> bool:
    """Returns True if invoice_number already exists in DB."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM invoices WHERE invoice_number = %s", (invoice_number,))
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conn.close()


def save_invoice(invoice: Invoice) -> int:
    """Insert invoice into DB, return new row id."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO invoices
              (invoice_number, vendor_name, invoice_date, gst_number,
               subtotal, tax_amount, total_amount, file_name, processing_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            invoice.invoice_number,
            invoice.vendor_name,
            invoice.invoice_date,
            invoice.gst_number,
            invoice.subtotal,
            invoice.tax_amount,
            invoice.total_amount,
            invoice.file_name,
            invoice.processing_time or datetime.now(),
        ))
        conn.commit()
        log_info(f"Saved invoice {invoice.invoice_number} (id={cursor.lastrowid})")
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def write_log(log: ProcessingLog):
    """Insert a processing log record."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO processing_logs (file_name, status, error_message)
            VALUES (%s, %s, %s)
        """, (log.file_name, log.status, log.error_message))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_all_invoices() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM invoices ORDER BY created_at DESC")
        rows = cursor.fetchall()
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
        return rows
    finally:
        cursor.close()
        conn.close()


def get_invoice_by_id(invoice_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM invoices WHERE id = %s", (invoice_id,))
        row = cursor.fetchone()
        if row:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
        return row
    finally:
        cursor.close()
        conn.close()


def search_invoices(query: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        like = f"%{query}%"
        cursor.execute("""
            SELECT * FROM invoices
            WHERE invoice_number LIKE %s
               OR vendor_name LIKE %s
               OR CAST(invoice_date AS CHAR) LIKE %s
            ORDER BY created_at DESC
        """, (like, like, like))
        rows = cursor.fetchall()
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
        return rows
    finally:
        cursor.close()
        conn.close()


def get_all_logs() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM processing_logs ORDER BY processed_at DESC LIMIT 200")
        rows = cursor.fetchall()
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
        return rows
    finally:
        cursor.close()
        conn.close()


def get_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) as total FROM invoices")
        total = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as cnt, status FROM processing_logs GROUP BY status")
        status_rows = cursor.fetchall()
        status_map = {r["status"]: r["cnt"] for r in status_rows}

        cursor.execute("SELECT SUM(total_amount) as grand_total FROM invoices")
        grand = cursor.fetchone()["grand_total"] or 0

        return {
            "total_invoices": total,
            "grand_total_amount": float(grand),
            "processing_summary": status_map,
        }
    finally:
        cursor.close()
        conn.close()
