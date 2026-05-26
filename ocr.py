import os
import re
import logging
from PIL import Image
import pdfplumber
from pdf2image import convert_from_path
import sys
import pytesseract

logger = logging.getLogger("ocr_extractor")

# --- Configurable paths via environment variables (issue #22) ---
if sys.platform.startswith('win'):
    _default_tesseract = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    _default_tesseract = 'tesseract'  # Assumes it's on PATH on Linux/Docker

TESSERACT_CMD = os.environ.get("TESSERACT_CMD", _default_tesseract)
POPPLER_PATH = os.environ.get("POPPLER_PATH", "")  # Empty = auto-detect or system PATH

if os.path.exists(TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    logger.info(f"Configured Tesseract path: {TESSERACT_CMD}")
elif TESSERACT_CMD != 'tesseract':
    logger.warning(f"Tesseract not found at configured path: {TESSERACT_CMD}")


def find_poppler_path() -> str | None:
    """Auto-detects Poppler bin directory. Returns configured path, auto-detected path, or None."""
    # Check environment variable first
    if POPPLER_PATH and os.path.exists(POPPLER_PATH):
        return POPPLER_PATH

    if not sys.platform.startswith('win'):
        return None  # On Linux/Docker, poppler-utils is typically on PATH
        
    search_dirs = [
        r'C:\Program Files\poppler\bin',
        r'C:\Program Files (x86)\poppler\bin',
        r'C:\poppler\bin',
        os.path.expandvars(r'%USERPROFILE%\poppler\bin'),
    ]
    for d in search_dirs:
        if os.path.exists(os.path.join(d, 'pdftoppm.exe')):
            return d
            
    # Search Program Files for any directory containing 'poppler' and having a 'bin' folder
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
    Cleans up extracted text:
    - Normalizes spacing and line endings.
    - Removes excessive consecutive blank lines.
    - Strips leading/trailing whitespace.
    """
    if not text:
        return ""
    # Replace multiple spaces with a single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Replace three or more newlines with double newlines (keeps paragraph separation)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_text_from_txt(file_path: str) -> str:
    """Reads raw text from a TXT file."""
    logger.info(f"Reading text file: {file_path}")
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_text_from_image(file_path: str) -> str:
    """Runs OCR on an image file (PNG, JPG, etc.)."""
    logger.info(f"Performing OCR on image: {file_path}")
    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img)
        return text
    except Exception as e:
        logger.error(f"Error during image OCR for {file_path}: {e}")
        raise e


def _get_pdf_page_count(file_path: str) -> int:
    """Returns the total number of pages in a PDF using pdfplumber."""
    try:
        with pdfplumber.open(file_path) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0


def extract_pages_from_pdf(file_path: str) -> list[dict]:
    """
    Extracts pages with page numbers from a PDF.
    First tries fast native text extraction page-by-page.
    If native extraction yields little text, falls back to OCR.
    OCR processes one page at a time to avoid loading all pages into memory (issue #17).
    Returns a list of dicts: [{'page': int, 'text': str}]
    """
    logger.info(f"Processing PDF: {file_path}")
    pages_data = []
    
    # 1. Try native text extraction page-by-page
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    pages_data.append({
                        "page": page_num,
                        "text": normalize_text(page_text)
                    })
    except Exception as e:
        logger.warning(f"Native PDF extraction failed/errored for {file_path}: {e}")
    
    full_native_text = "".join([p["text"] for p in pages_data])
    
    # If we extracted a reasonable amount of text, return it
    if len(full_native_text.strip()) > 100:
        logger.info(f"Successfully extracted native text from PDF: {file_path} ({len(full_native_text)} chars)")
        return pages_data
        
    # 2. Fall back to OCR — process ONE PAGE AT A TIME to limit memory (issue #17)
    logger.info(f"Native extraction returned too little text. Falling back to OCR for PDF: {file_path}")
    pages_data = []
    try:
        poppler_dir = find_poppler_path()
        if poppler_dir:
            logger.info(f"Using Poppler path: {poppler_dir}")

        total_pages = _get_pdf_page_count(file_path)
        if total_pages == 0:
            # Fallback: try converting page 1 to detect errors early
            total_pages = 1
            
        logger.info(f"OCR: processing {total_pages} pages one at a time.")
        for page_num in range(1, total_pages + 1):
            logger.info(f"Running OCR on page {page_num}/{total_pages}")
            try:
                convert_kwargs = {
                    "pdf_path": file_path,
                    "dpi": 150,
                    "first_page": page_num,
                    "last_page": page_num,
                }
                if poppler_dir:
                    convert_kwargs["poppler_path"] = poppler_dir
                    
                page_images = convert_from_path(**convert_kwargs)
                if page_images:
                    page_text = pytesseract.image_to_string(page_images[0])
                    # Explicitly close/delete the PIL image to free memory
                    page_images[0].close()
                    del page_images
                    
                    if page_text:
                        pages_data.append({
                            "page": page_num,
                            "text": normalize_text(page_text)
                        })
            except Exception as page_err:
                logger.warning(f"OCR failed for page {page_num}: {page_err}")
                continue
                
        return pages_data
    except Exception as e:
        logger.error(f"Failed to perform OCR on PDF {file_path}: {e}")
        raise e


def extract_text_from_pdf(file_path: str) -> str:
    """Legacy helper: Extracts text from a PDF as a single string."""
    pages = extract_pages_from_pdf(file_path)
    return "\n".join([p["text"] for p in pages])


def extract_document_pages(file_path: str) -> list[dict]:
    """
    Master function to extract text page-by-page from a file based on its extension.
    Supported extensions: .pdf, .txt, .png, .jpg, .jpeg, .tiff
    Returns a list of dicts: [{'page': int, 'text': str}]
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.txt':
        raw_text = extract_text_from_txt(file_path)
        return [{"page": 1, "text": normalize_text(raw_text)}]
    elif ext == '.pdf':
        return extract_pages_from_pdf(file_path)
    elif ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        raw_text = extract_text_from_image(file_path)
        return [{"page": 1, "text": normalize_text(raw_text)}]
    else:
        # Generic fallback: try reading as text
        logger.warning(f"Unsupported extension '{ext}'. Trying generic text reader.")
        raw_text = extract_text_from_txt(file_path)
        return [{"page": 1, "text": normalize_text(raw_text)}]


def extract_document_text(file_path: str) -> str:
    """Legacy helper: Master function to extract all text as a single string."""
    pages = extract_document_pages(file_path)
    return "\n".join([p["text"] for p in pages])


if __name__ == "__main__":
    # Test script to run basic validations
    print("OCR Module Initialized.")
