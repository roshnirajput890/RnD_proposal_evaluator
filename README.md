# AI-Based Multi-Agent R&D Proposal Evaluation System

**Brick 2: PDF Upload & Text Extraction**

This repository contains the working implementation for the **AI-Based Multi-Agent R&D Proposal Evaluation System**.

In this system, a user uploads a research and development (R&D) proposal PDF, specialized AI evaluation agents (Novelty, Technical Feasibility, Financial Viability, and Strategic Impact) analyze it, and a coordinator synthesizes a comprehensive report for human review.

---

## Current Status: Brick 2 (PDF Upload & Text Extraction)

### What Brick 2 Implements:
- **Frontend (React + Vite, Vanilla CSS)**:
  - Drag-and-drop and file-browser PDF picker (accepts `.pdf`).
  - Selected file metadata display (filename, size) with remove/change option.
  - "Upload & Analyze" action button (disabled while extracting or when no file is selected).
  - Clean animated loading indicators while extraction proceeds in memory.
  - Extraction results dashboard:
    - Summary metrics: total pages, total character count, processing mode.
    - Extracted text preview area displaying the first ~1,500 characters of extracted text, with a toggle to view the full text.
    - Collapsible page-by-page breakdown displaying each page's extracted text and character count.
  - User-friendly error alert banners for all validation and processing issues.
- **Backend (FastAPI, Python)**:
  - `POST /api/upload`: Multipart endpoint for receiving PDF proposals.
  - Modular extraction service in [`backend/app/services/pdf_service.py`](backend/app/services/pdf_service.py) using **PyMuPDF (`fitz`)**.
  - **Strict in-memory processing**: No uploaded files or temporary files are saved to disk.
  - Page-by-page text extraction returning:
    - `filename`: original name of the proposal.
    - `page_count`: number of pages.
    - `char_count`: total characters extracted.
    - `pages`: list of `{ "page_number": int, "text": str }`.
    - `full_text`: combined extracted text.
  - Robust validation and user-friendly error handling:
    - **No file selected / empty file**: 400 Bad Request.
    - **Non-PDF validation**: Checks MIME type AND verifies the file starts with `%PDF` magic bytes.
    - **File size limit**: Enforces maximum size of 10 MB.
    - **Password-protected / encrypted PDF**: Detects encryption and requests unencrypted document.
    - **Corrupted PDF**: Detects malformed PDF stream and returns a clean error message.
    - **Scanned image / No extractable text**: Detects PDFs without digital text and advises that OCR is not supported yet.
    - **Unexpected server error**: Catches and returns clean 500 error details.

---

## Project Structure

```text
R&D_analyzer/
├── .gitignore                    # Ignores venv, node_modules, .env, dist, __pycache__
├── README.md                     # Project documentation, setup, and test guide
├── backend/
│   ├── app/
│   │   ├── __init__.py           # Backend package initializer
│   │   ├── main.py               # FastAPI entry point, CORS & router mounting
│   │   ├── routes/
│   │   │   ├── __init__.py       # Routes exports
│   │   │   ├── health.py         # Health check (GET /api/health)
│   │   │   └── upload.py         # PDF upload endpoint (POST /api/upload)
│   │   └── services/
│   │       ├── __init__.py       # Services exports
│   │       └── pdf_service.py    # In-memory PyMuPDF extraction & validation
│   ├── generate_test_pdfs.py     # Generates test PDFs covering all edge cases
│   ├── test_brick2.py            # Automated unit test suite (9 test cases)
│   ├── test_files/               # Pre-generated sample PDFs for testing
│   │   ├── empty_zero_bytes.pdf  # 0-byte file
│   │   ├── not_a_pdf.pdf         # Text file pretending to be PDF
│   │   ├── password_protected.pdf# AES-256 encrypted PDF
│   │   ├── scanned_image_like.pdf# Blank PDF with no digital text
│   │   └── valid_proposal.pdf    # 3-page valid proposal
│   ├── requirements.txt          # Python dependencies (FastAPI, Uvicorn, PyMuPDF, python-multipart)
│   └── venv/                     # Python virtual environment
└── frontend/
    ├── index.html                # HTML entry template
    ├── package.json              # Frontend scripts & dependencies
    ├── vite.config.js            # Vite configuration (port 5173)
    └── src/
        ├── App.css               # Vanilla CSS layout, status, upload, & preview styles
        ├── App.jsx               # React UI for health check, upload, & preview
        ├── config.js             # Centralized API base URL config (http://localhost:8000)
        ├── index.css             # Base reset & design variables
        └── main.jsx              # React mounting script
```

---

## Prerequisites

- **Python**: Version 3.10 or higher
- **Node.js**: Version 18 or higher (with npm)

---

## Step-by-Step Setup & Run Instructions

Open two terminal windows: one for the **Backend** and one for the **Frontend**.

### 1. Backend (FastAPI on Port 8000)

#### On Windows (PowerShell):
```powershell
cd backend
.\venv\Scripts\Activate.ps1
# (If script execution is disabled: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### On Windows (Command Prompt):
```cmd
cd backend
venv\Scripts\activate.bat
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### On macOS & Linux (Bash / Zsh):
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend URLs:
- **API Base**: [http://localhost:8000](http://localhost:8000)
- **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### 2. Frontend (Vite + React on Port 5173)

Open a second terminal:

#### On Windows / macOS / Linux:
```bash
cd frontend
npm install
npm run dev
```

Frontend URL:
- **Web App**: [http://localhost:5173](http://localhost:5173)

---

## How to Test Brick 2

### Method 1: Automated Unit Tests
Run the standalone test suite in the backend terminal:
```bash
cd backend
python test_brick2.py
```
This executes 9 automated tests covering:
1. Valid multi-page PDF text extraction
2. Missing filename error
3. Empty file (0 bytes) error
4. File size over 10 MB error
5. Non-PDF MIME type error
6. Missing `%PDF` header error
7. Password-protected PDF error
8. Corrupted PDF stream error
9. PDF with no extractable text (scanned image) error

### Method 2: Interactive Testing via the Web UI
Sample test files have been pre-generated in [`backend/test_files/`](backend/test_files/):

1. **Valid Proposal Test**:
   - In the browser at [http://localhost:5173](http://localhost:5173), drag and drop or browse for `backend/test_files/valid_proposal.pdf`.
   - Click **"Upload & Analyze"**.
   - Notice the loading indicator, followed by the complete results:
     - Total Pages: 3
     - Total Characters: ~1,116
     - Extracted Text Preview showing the first ~1,500 characters
     - Expandable Page Breakdown (Page 1, Page 2, Page 3).
2. **Scanned / Image-Only PDF Test**:
   - Upload `backend/test_files/scanned_image_like.pdf`.
   - Click **"Upload & Analyze"**.
   - Red error alert displays: *"No extractable text found in this PDF. It may be a scanned image or contain only pictures. OCR (Optical Character Recognition) is not supported yet."*
3. **Password-Protected PDF Test**:
   - Upload `backend/test_files/password_protected.pdf`.
   - Click **"Upload & Analyze"**.
   - Red error alert displays: *"The PDF is password-protected. Please remove the password and re-upload."*
4. **Invalid File Test**:
   - Upload `backend/test_files/not_a_pdf.pdf`.
   - Red error alert displays explaining the file does not start with `%PDF`.
5. **Empty File Test**:
   - Upload `backend/test_files/empty_zero_bytes.pdf`.
   - Red error alert displays: *"The selected file is empty (0 bytes)..."*
