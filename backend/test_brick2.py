"""
Test suite for Brick 2: PDF Validation & Text Extraction.
Tests all requirements and edge cases in pdf_service and upload route.
"""
import io
import pymupdf as fitz
from app.services.pdf_service import (
    PDFProcessingError,
    validate_pdf_upload,
    extract_text_from_pdf,
    MAX_FILE_SIZE_BYTES,
)


def create_sample_pdf(pages_text: list[str]) -> bytes:
    """Creates an in-memory PDF with given text per page."""
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((50, 72), text, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_encrypted_pdf(text: str, password: str = "secret") -> bytes:
    """Creates a password-protected PDF in memory."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=12)
    # Encrypt document
    perm = int(
        fitz.PDF_PERM_ACCESSIBILITY
        | fitz.PDF_PERM_PRINT
        | fitz.PDF_PERM_COPY
        | fitz.PDF_PERM_ANNOTATE
    )
    encrypt_method = fitz.PDF_ENCRYPT_AES_256
    pdf_bytes = doc.tobytes(
        encryption=encrypt_method,
        owner_pw=password,
        user_pw=password,
        permissions=perm,
    )
    doc.close()
    return pdf_bytes


def create_blank_pdf(num_pages: int = 1) -> bytes:
    """Creates a PDF with blank pages (no extractable text)."""
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def run_all_tests():
    print("=== Running Brick 2 PDF Service Verification Tests ===\n")
    passed = 0
    total = 0

    # Test 1: Valid multi-page PDF extraction
    total += 1
    try:
        page_1 = "Proposal Title: Autonomous Drone Fleet for Agricultural Monitoring.\nNovelty: Novel swarm coordination algorithms."
        page_2 = "Technical Feasibility: Built on ROS2 and custom vision pipelines.\nBudget: $150,000 across 18 months."
        pdf_bytes = create_sample_pdf([page_1, page_2])
        validate_pdf_upload("sample_proposal.pdf", "application/pdf", pdf_bytes)
        result = extract_text_from_pdf("sample_proposal.pdf", pdf_bytes)

        assert result["filename"] == "sample_proposal.pdf"
        assert result["page_count"] == 2
        assert len(result["pages"]) == 2
        assert result["pages"][0]["page_number"] == 1
        assert "Autonomous Drone Fleet" in result["pages"][0]["text"]
        assert result["pages"][1]["page_number"] == 2
        assert "Technical Feasibility" in result["pages"][1]["text"]
        assert result["char_count"] > 0
        assert "Autonomous Drone Fleet" in result["full_text"]
        print("[PASS] Test 1: Valid 2-page PDF text extracted page-by-page correctly.")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 1 Failed: {e}")

    # Test 2: Validation - No file selected (empty filename)
    total += 1
    try:
        validate_pdf_upload("", "application/pdf", b"%PDF-dummy")
        print("[FAIL] Test 2: Should have raised error for empty filename")
    except PDFProcessingError as e:
        assert e.status_code == 400
        assert "No file selected" in e.message
        print(f"[PASS] Test 2: Correctly caught missing filename: '{e.message}'")
        passed += 1

    # Test 3: Validation - Empty file (0 bytes)
    total += 1
    try:
        validate_pdf_upload("empty.pdf", "application/pdf", b"")
        print("[FAIL] Test 3: Should have raised error for 0 bytes")
    except PDFProcessingError as e:
        assert e.status_code == 400
        assert "empty" in e.message.lower()
        print(f"[PASS] Test 3: Correctly caught empty file: '{e.message}'")
        passed += 1

    # Test 4: Validation - File over 10 MB
    total += 1
    try:
        huge_bytes = b"%PDF" + b"0" * (MAX_FILE_SIZE_BYTES + 1024)
        validate_pdf_upload("huge.pdf", "application/pdf", huge_bytes)
        print("[FAIL] Test 4: Should have raised error for file > 10MB")
    except PDFProcessingError as e:
        assert e.status_code == 400
        assert "10 MB" in e.message
        print(f"[PASS] Test 4: Correctly caught >10MB file: '{e.message}'")
        passed += 1

    # Test 5: Validation - Non-PDF content type
    total += 1
    try:
        validate_pdf_upload("image.png", "image/png", b"%PDF-dummy")
        print("[FAIL] Test 5: Should have rejected non-PDF content type")
    except PDFProcessingError as e:
        assert e.status_code == 400
        assert "Only PDF documents are accepted" in e.message
        print(f"[PASS] Test 5: Correctly rejected non-PDF MIME type: '{e.message}'")
        passed += 1

    # Test 6: Validation - Non-PDF magic bytes (missing %PDF header)
    total += 1
    try:
        fake_pdf = b"NOT_A_PDF_CONTENT"
        validate_pdf_upload("fake.pdf", "application/pdf", fake_pdf)
        print("[FAIL] Test 6: Should have rejected file missing %PDF header")
    except PDFProcessingError as e:
        assert e.status_code == 400
        assert "%PDF" in e.message
        print(f"[PASS] Test 6: Correctly rejected file without %PDF header: '{e.message}'")
        passed += 1

    # Test 7: Password-protected PDF
    total += 1
    try:
        enc_bytes = create_encrypted_pdf("Confidential Research Proposal", password="secret_password")
        validate_pdf_upload("encrypted.pdf", "application/pdf", enc_bytes)
        extract_text_from_pdf("encrypted.pdf", enc_bytes)
        print("[FAIL] Test 7: Should have rejected password-protected PDF")
    except PDFProcessingError as e:
        assert e.status_code == 400
        assert "password-protected" in e.message.lower()
        print(f"[PASS] Test 7: Correctly handled password-protected PDF: '{e.message}'")
        passed += 1

    # Test 8: Corrupt PDF file
    total += 1
    try:
        corrupt_bytes = b"%PDF-1.4\n%corrupt-garbage-bytes\n"
        validate_pdf_upload("corrupt.pdf", "application/pdf", corrupt_bytes)
        extract_text_from_pdf("corrupt.pdf", corrupt_bytes)
        print("[FAIL] Test 8: Should have rejected corrupt PDF")
    except PDFProcessingError as e:
        assert e.status_code == 400
        assert "corrupted" in e.message.lower() or "read" in e.message.lower()
        print(f"[PASS] Test 8: Correctly handled corrupted PDF: '{e.message}'")
        passed += 1

    # Test 9: PDF with no extractable text (e.g. blank / scanned without OCR)
    total += 1
    try:
        blank_bytes = create_blank_pdf(2)
        validate_pdf_upload("scanned.pdf", "application/pdf", blank_bytes)
        extract_text_from_pdf("scanned.pdf", blank_bytes)
        print("[FAIL] Test 9: Should have rejected PDF with no extractable text")
    except PDFProcessingError as e:
        assert e.status_code == 400
        assert "no extractable text" in e.message.lower()
        assert "ocr" in e.message.lower()
        print(f"[PASS] Test 9: Correctly reported no extractable text / OCR not supported: '{e.message}'")
        passed += 1

    print(f"\n==========================================")
    print(f"Test Summary: {passed}/{total} tests passed successfully!")
    print(f"==========================================")


if __name__ == "__main__":
    run_all_tests()
