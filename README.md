# InvoiceFlow — Invoice Processing & Management

Process invoices (PDF/JPG/PNG), store structured invoice data in **MySQL**,
and manage everything through a clean business dashboard.

---

## Quick Start

### 1. Clone / extract the project

```
invoice_processor/
├── app.py
├── config/db_config.py
├── services/
│   ├── ocr_service.py      ← Document extraction service
│   ├── processor.py        ← Main pipeline
│   ├── parser.py
│   ├── validator.py
│   ├── database.py
│   ├── file_handler.py
│   └── logger.py
├── models/invoice_model.py
├── static/index.html       ← Dashboard UI
├── invoices/               ← Drop invoices here
├── processed/              ← Auto-moved on success
├── failed/                 ← Auto-moved on failure
├── logs/                   ← Log files
└── .env
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> Also needs **poppler** for PDF support:
> - Ubuntu/Debian: `sudo apt-get install poppler-utils`
> - macOS: `brew install poppler`
> - Windows: Download from https://github.com/oschwartz10612/poppler-windows

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your credentials:
```

```env
GEMINI_API_KEY=your_key
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=invoice_db
```

### 4. Create MySQL database

```sql
/usr/local/mysql/bin/mysql -u root -p

CREATE DATABASE invoice_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
Tables are created automatically on first run.

### 5. Run the server

```bash
cd invoice_processor
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** in your browser.

---

## Usage

### Dashboard
- Live stats: total invoices, processed invoices, pending invoices, and volume
- Recent invoice table
- Analytics sections for monthly volume and processing health

### Upload Invoice
| Mode | Description |
|------|-------------|
| **Single File** | Upload & process one invoice immediately |
| **Bulk Upload** | Upload & process multiple files at once |
| **Process Folder** | Drop files into `invoices/` and trigger batch processing |

### All Invoices
- Search by invoice number, vendor name, or date
- Export to CSV

### Processing Logs
- Full audit trail of every file processed

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload & process single invoice |
| `POST` | `/bulk-upload` | Upload & process multiple invoices |
| `POST` | `/process-folder` | Process all files in `invoices/` folder |
| `GET`  | `/invoices?q=` | List/search invoices |
| `GET`  | `/invoice/{id}` | Get invoice by ID |
| `GET`  | `/logs` | Get processing logs |
| `GET`  | `/stats` | Get summary statistics |

---

## How It Works

```
Upload File
    │
    ▼
Document Extraction ─── extracts structured invoice fields
    │
    ▼
Parser ─── normalizes dates & amounts
    │
    ▼
Validator ─── checks invoice #, amount > 0, date present
    │
    ▼
Duplicate Check ─── queries MySQL by invoice_number
    │
    ▼
MySQL INSERT
    │
    ├── SUCCESS → move to processed/
    └── FAILURE → move to failed/
         └── log error in DB + log file
```

---

## Notes

- Multi-page PDFs: only page 1 is processed (extend in `ocr_service.py`)
- GST validation is a soft check (warns but does not reject non-GST invoices)
