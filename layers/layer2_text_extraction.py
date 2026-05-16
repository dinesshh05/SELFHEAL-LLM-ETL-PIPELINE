from __future__ import annotations

from models.schemas import DocumentType, PipelineContext
from utils.logger import log_error, log_layer, log_success, log_warning

# Extractors
def _extract_text_file(path: str) -> str:
    """Read a plain text / markdown file."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _extract_pdf(path: str) -> str:
    """
    Extract all text from a PDF using PyMuPDF.
    Falls back page-by-page to handle encrypted/partial PDFs.
    """
    try:
        import fitz  # type:ignore
    except ImportError:
        raise ImportError(
            "PyMuPDF is required for PDF extraction. "
            "Install it with: pip install pymupdf"
        )

    doc   = fitz.open(path)
    pages = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if text.strip():
            pages.append(f"--- Page {page_num} ---\n{text.strip()}")
    doc.close()

    if not pages:
        raise ValueError("PDF contains no extractable text. May be image-only; use OCR.")

    return "\n\n".join(pages)


def _extract_image(_path: str) -> str:
    """
    Stub for image/scanned document OCR.
    Future: call pytesseract or Claude Vision API here.
    """
    raise NotImplementedError(
        "Image OCR is not yet implemented. "
        "Future plan: integrate pytesseract or Claude Vision API."
    )

# Public API


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 2 entry point.

    Reads ctx.source_file according to ctx.document_type,
    writes clean text into ctx.raw_text, and returns ctx.
    """
    log_layer("TEXT EXTRACTION", f"Extracting from {ctx.document_type.value} -> {ctx.source_file}")

    try:
        if ctx.document_type == DocumentType.TEXT:
            raw_text = _extract_text_file(ctx.source_file)

        elif ctx.document_type == DocumentType.PDF:
            raw_text = _extract_pdf(ctx.source_file)

        elif ctx.document_type == DocumentType.IMAGE:
            raw_text = _extract_image(ctx.source_file)

        else:
            raise ValueError(f"No extractor for document type: {ctx.document_type}")

        # ── Quality guard ────────────────────
        if len(raw_text.strip()) < 50:
            log_warning("Extracted text is suspiciously short - may be low quality")

        ctx.raw_text = raw_text.strip()
        log_success(f"Extracted {len(ctx.raw_text):,} characters of text")

    except (NotImplementedError, ValueError, ImportError) as exc:
        log_error(f"Text extraction failed: {exc}")
        raise

    return ctx
