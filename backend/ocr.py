import os
import re
import logging
from PIL import Image, ImageSequence
import pdfplumber
from pdf2image import convert_from_path, pdfinfo_from_path
import sys
import pytesseract

logger = logging.getLogger("ocr_extractor")

# A PDF page with less native text than this is taken for a scan - or a scan
# whose text layer holds only a stamp or header - and read through OCR.
MIN_PAGE_CHARS = 100
# Tesseract's accuracy on small print drops well below 300 dpi.
OCR_DPI = 300

if sys.platform.startswith('win'):
    _default_tesseract = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    _default_tesseract = 'tesseract'

TESSERACT_CMD = os.environ.get("TESSERACT_CMD", _default_tesseract)
POPPLER_PATH = os.environ.get("POPPLER_PATH", "") 

if os.path.exists(TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    logger.info(f"Configured Tesseract path: {TESSERACT_CMD}")
elif TESSERACT_CMD != 'tesseract':
    logger.warning(f"Tesseract not found at configured path: {TESSERACT_CMD}")


def find_poppler_path() -> str | None:

    if POPPLER_PATH and os.path.exists(POPPLER_PATH):
        return POPPLER_PATH

    if not sys.platform.startswith('win'):
        return None 
        
    search_dirs = [
        r'C:\Program Files\poppler\bin',
        r'C:\Program Files (x86)\poppler\bin',
        r'C:\poppler\bin',
        os.path.expandvars(r'%USERPROFILE%\poppler\bin'),
    ]
    for d in search_dirs:
        if os.path.exists(os.path.join(d, 'pdftoppm.exe')):
            return d
            
    try:
        prog_files = r'C:\Program Files'
        if os.path.exists(prog_files):
            for entry in os.listdir(prog_files):
                if 'poppler' in entry.lower():
                    full_path = os.path.join(prog_files, entry, 'bin')
                    if os.path.exists(os.path.join(full_path, 'pdftoppm.exe')):
                        return full_path
    except Exception:
        pass
        
    return None


def normalize_text(text: str) -> str:
    """
    Normalizes spacing and line endings.
    Removes consecutive blank lines.
    Strips whitespace.
    """
    if not text:
        return ""

    text = re.sub(r'[ \t]+', ' ', text)

    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_text_from_txt(file_path: str) -> str:
    logger.info(f"Reading text file: {file_path}")
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_pages_from_image(file_path: str) -> list[dict]:
    """One page per frame: a scanned TIFF often holds the whole document."""
    logger.info(f"Performing OCR on image: {file_path}")
    pages = []
    with Image.open(file_path) as img:
        for page_num, frame in enumerate(ImageSequence.Iterator(img), 1):
            text = normalize_text(pytesseract.image_to_string(frame.copy()))
            if text:
                pages.append({"page": page_num, "text": text})
    return pages


def _ocr_pdf_page(file_path: str, page_num: int, poppler_dir: str | None) -> str:
    # One page at a time, so a large scan cannot exhaust memory.
    images = convert_from_path(file_path, dpi=OCR_DPI, first_page=page_num, last_page=page_num,
                               poppler_path=poppler_dir)
    try:
        return pytesseract.image_to_string(images[0]) if images else ""
    finally:
        for image in images:
            image.close()


def extract_pages_from_pdf(file_path: str) -> list[dict]:
    """Native text where a page has a text layer, OCR where it has too little.

    Decided page by page: a scanned contract with a digital cover page, or a
    signed scan carrying a text stamp, has a text layer on some pages only.
    """
    logger.info(f"Processing PDF: {file_path}")
    poppler_dir = find_poppler_path()
    try:
        with pdfplumber.open(file_path) as pdf:
            native = [page.extract_text() or "" for page in pdf.pages]
    except Exception as e:
        logger.warning(f"Native PDF extraction failed for {file_path}, reading every page through OCR: {e}")
        native = [""] * pdfinfo_from_path(file_path, poppler_path=poppler_dir)["Pages"]

    pages, ocr_pages = [], 0
    for page_num, raw in enumerate(native, 1):
        text = normalize_text(raw)
        if len(text) < MIN_PAGE_CHARS:
            ocr_pages += 1
            try:
                ocr_text = normalize_text(_ocr_pdf_page(file_path, page_num, poppler_dir))
            except Exception as e:
                logger.warning(f"OCR failed for page {page_num} of {file_path}: {e}")
                ocr_text = ""
            text = max(text, ocr_text, key=len)
        if text:
            pages.append({"page": page_num, "text": text})
    logger.info(f"Extracted {len(pages)} of {len(native)} pages from {file_path}, {ocr_pages} through OCR")
    return pages


def extract_document_pages(file_path: str) -> list[dict]:
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.txt':
        raw_text = extract_text_from_txt(file_path)
        return [{"page": 1, "text": normalize_text(raw_text)}]
    elif ext == '.pdf':
        return extract_pages_from_pdf(file_path)
    elif ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp']:
        return extract_pages_from_image(file_path)
    else:
        logger.warning(f"Unsupported extension '{ext}'. Trying generic text reader.")
        raw_text = extract_text_from_txt(file_path)
        return [{"page": 1, "text": normalize_text(raw_text)}]
