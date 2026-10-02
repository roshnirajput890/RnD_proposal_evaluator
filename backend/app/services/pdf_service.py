"""
PDF Extraction Service.

Handles in-memory validation and page-by-page text extraction from uploaded PDF files
using PyMuPDF (fitz). Files are strictly processed in memory without saving to disk.
"""
from typing import Dict, Any, List
try:
    import pymupdf as fitz
except ImportError:
    import fitz


# Constants
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
PDF_MAGIC_BYTES = b"%PDF"


class PDFProcessingError(Exception):
    """Custom exception raised when PDF validation or extraction fails."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_pdf_upload(filename: str, content_type: str, file_bytes: bytes) -> None:
    """
    Validates uploaded file properties:
    - Verifies file is not empty
    - Checks MIME content type
    - Verifies %PDF magic byte header
    - Checks file size against the 10 MB limit

    Raises:
        PDFProcessingError: If any validation rule fails.
    """
    if not filename or not filename.strip():
        raise PDFProcessingError(
            "No file selected. Please select an R&D proposal PDF file.",
            status_code=400,
        )

    if not file_bytes or len(file_bytes) == 0:
        raise PDFProcessingError(
            "The selected file is empty (0 bytes). Please upload a valid PDF proposal.",
            status_code=400,
        )

    # Check maximum file size (10 MB)
    file_size = len(file_bytes)
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = round(file_size / (1024 * 1024), 2)
        raise PDFProcessingError(
            f"File size exceeds the 10 MB limit (uploaded file is {size_mb} MB). "
            "Please upload a smaller document.",
            status_code=400,
        )

    # Check content type and magic bytes
    # Accept standard application/pdf as well as application/x-pdf
    valid_content_types = ["application/pdf", "application/x-pdf"]
    is_pdf_content_type = content_type and any(
        content_type.lower().startswith(ct) for ct in valid_content_types
    )

    if not is_pdf_content_type:
        raise PDFProcessingError(
            f"Invalid file type '{content_type}'. Only PDF documents are accepted.",
            status_code=400,
        )

    if not file_bytes.startswith(PDF_MAGIC_BYTES):
        raise PDFProcessingError(
            "Invalid file content. The file does not start with the required '%PDF' header.",
            status_code=400,
        )


def extract_text_from_pdf(filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """
    Extracts text page-by-page from an in-memory PDF document.

    Args:
        filename: Name of the uploaded file.
        file_bytes: Raw bytes of the PDF.

    Returns:
        Dict containing:
            - filename: str
            - page_count: int
            - char_count: int
            - pages: List[Dict[str, Any]] with 'page_number' and 'text'
            - full_text: str

    Raises:
        PDFProcessingError: If the PDF is corrupted, password-protected,
                            or contains no extractable text.
    """
    doc = None
    try:
        # Open PDF strictly in memory from byte stream
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as err:
        raise PDFProcessingError(
            f"The PDF file is corrupted or could not be read: {str(err)}",
            status_code=400,
        ) from err

    try:
        # Check if the document is password-protected / encrypted
        if doc.is_encrypted:
            raise PDFProcessingError(
                "The PDF is password-protected. Please remove the password and re-upload.",
                status_code=400,
            )

        page_count = len(doc)
        if page_count == 0:
            raise PDFProcessingError(
                "The PDF document contains 0 pages.",
                status_code=400,
            )

        pages: List[Dict[str, Any]] = []
        full_text_parts: List[str] = []

        # Extract text page by page
        for page_index in range(page_count):
            page_num = page_index + 1
            try:
                page = doc.load_page(page_index)
                page_text = page.get_text() or ""
            except Exception as page_err:
                raise PDFProcessingError(
                    f"Failed to read page {page_num}: {str(page_err)}",
                    status_code=400,
                ) from page_err

            pages.append({
                "page_number": page_num,
                "text": page_text,
            })
            full_text_parts.append(page_text)

        full_text = "\n\n".join(full_text_parts)
        stripped_text = full_text.strip()

        # Check for empty / scanned document with no extractable text
        if not stripped_text:
            raise PDFProcessingError(
                "No extractable text found in this PDF. It may be a scanned image "
                "or contain only pictures. OCR (Optical Character Recognition) is not supported yet.",
                status_code=400,
            )

        return {
            "filename": filename,
            "page_count": page_count,
            "char_count": len(full_text),
            "pages": pages,
            "full_text": full_text,
        }

    finally:
        if doc is not None:
            doc.close()
