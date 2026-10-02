"""
Helper script to generate sample test PDFs for manual and automated testing of Brick 2.
Generates:
1. test_files/valid_proposal.pdf (Valid 3-page R&D proposal)
2. test_files/scanned_image_like.pdf (Blank 2-page PDF with no extractable text)
3. test_files/password_protected.pdf (AES-256 encrypted PDF)
4. test_files/not_a_pdf.pdf (Invalid PDF content without %PDF header)
5. test_files/empty_zero_bytes.pdf (0-byte empty file)
"""
import os
import pymupdf as fitz


def create_test_suite_files():
    out_dir = os.path.join(os.path.dirname(__file__), "test_files")
    os.makedirs(out_dir, exist_ok=True)

    # 1. Valid Proposal PDF (3 pages)
    doc_valid = fitz.open()
    # Page 1
    p1 = doc_valid.new_page()
    p1.insert_text(
        (50, 72),
        "PROJECT PROPOSAL: Next-Generation Quantum Key Distribution (QKD) Protocols\n\n"
        "Abstract:\n"
        "This project investigates post-quantum cryptographic primitives combined with\n"
        "high-efficiency satellite-to-ground quantum communications. Our objective is to\n"
        "demonstrate robust entanglement generation over turbulent atmospheric channels.\n\n"
        "Novelty:\n"
        "Existing QKD deployments rely on fiber links limited to ~100 km. We introduce a\n"
        "novel adaptive optics phase correction scheme operating at 1550 nm.\n",
        fontsize=11,
    )
    # Page 2
    p2 = doc_valid.new_page()
    p2.insert_text(
        (50, 72),
        "Technical Feasibility & Architecture:\n"
        "- Subsystem A: Entangled Photon Pair Source (SPDC crystal, 80 MHz repetition rate)\n"
        "- Subsystem B: Fast Steering Mirrors with closed-loop piezo actuation\n"
        "- Subsystem C: Superconducting Nanowire Single-Photon Detectors (SNSPDs)\n\n"
        "Risk Mitigation:\n"
        "Atmospheric turbulence models will be validated via horizontal ground-test link (12 km).\n",
        fontsize=11,
    )
    # Page 3
    p3 = doc_valid.new_page()
    p3.insert_text(
        (50, 72),
        "Budget & Milestones:\n"
        "- Phase 1 (Months 1-6): Optical bench prototype ($180,000)\n"
        "- Phase 2 (Months 7-14): Field testing and channel characterization ($250,000)\n"
        "- Phase 3 (Months 15-24): Synthesis of final evaluation report ($70,000)\n\n"
        "Total Grant Request: $500,000\n",
        fontsize=11,
    )
    doc_valid.save(os.path.join(out_dir, "valid_proposal.pdf"))
    doc_valid.close()

    # 2. Blank PDF with no extractable text (simulating scanned document without OCR)
    doc_blank = fitz.open()
    doc_blank.new_page()
    doc_blank.new_page()
    doc_blank.save(os.path.join(out_dir, "scanned_image_like.pdf"))
    doc_blank.close()

    # 3. Password-protected PDF
    doc_enc = fitz.open()
    pe = doc_enc.new_page()
    pe.insert_text((50, 72), "Confidential Proprietary Proposal", fontsize=12)
    perm = int(fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT)
    doc_enc.save(
        os.path.join(out_dir, "password_protected.pdf"),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="researcher123",
        user_pw="researcher123",
        permissions=perm,
    )
    doc_enc.close()

    # 4. Fake PDF (wrong header)
    with open(os.path.join(out_dir, "not_a_pdf.pdf"), "w", encoding="utf-8") as f:
        f.write("This is a plain text file pretending to be a PDF without the %PDF header.")

    # 5. Empty 0-byte file
    with open(os.path.join(out_dir, "empty_zero_bytes.pdf"), "wb") as f:
        pass

    print(f"Generated 5 test files in: {out_dir}")


if __name__ == "__main__":
    create_test_suite_files()
