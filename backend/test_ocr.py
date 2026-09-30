import os
import tempfile
from types import SimpleNamespace

from PIL import Image

import ocr

DIGITAL = "This Services Agreement is entered into by and between the parties named below. " * 3
SCANNED = "The Supplier shall maintain insurance with reputable insurers for the full term. " * 3


class _Pdf:
    def __init__(self, texts):
        self.pages = [SimpleNamespace(extract_text=lambda t=t: t) for t in texts]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_each_pdf_page_decides_for_itself():
    # A digital cover page, a page with no text layer, and a scan carrying a stamp.
    texts = [DIGITAL, None, "CONFIDENTIAL - Page 3"]
    ocr_calls = []
    real_pdfplumber, real_ocr_page = ocr.pdfplumber, ocr._ocr_pdf_page
    ocr.pdfplumber = SimpleNamespace(open=lambda path: _Pdf(texts))
    ocr._ocr_pdf_page = lambda path, page, poppler: ocr_calls.append(page) or f"{SCANNED}(page {page})"
    try:
        pages = ocr.extract_pages_from_pdf("contract.pdf")
    finally:
        ocr.pdfplumber, ocr._ocr_pdf_page = real_pdfplumber, real_ocr_page

    assert ocr_calls == [2, 3], ocr_calls  # the cover page keeps its text layer
    assert [p["page"] for p in pages] == [1, 2, 3]
    assert pages[0]["text"] == DIGITAL.strip()
    assert pages[2]["text"].endswith("(page 3)")  # OCR won over the stamp


def test_every_tiff_frame_is_a_page():
    path = os.path.join(tempfile.mkdtemp(), "scan.tiff")
    frames = [Image.new("L", (100 + i, 100), 255) for i in range(3)]
    frames[0].save(path, save_all=True, append_images=frames[1:])
    real = ocr.pytesseract.image_to_string
    ocr.pytesseract.image_to_string = lambda image: f"frame {image.size[0] - 100}"
    try:
        pages = ocr.extract_document_pages(path)
    finally:
        ocr.pytesseract.image_to_string = real
    assert pages == [{"page": 1, "text": "frame 0"}, {"page": 2, "text": "frame 1"}, {"page": 3, "text": "frame 2"}]


if __name__ == "__main__":
    test_each_pdf_page_decides_for_itself()
    test_every_tiff_frame_is_a_page()
    print("ok")
