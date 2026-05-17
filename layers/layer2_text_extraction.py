from __future__ import annotations

import re
import zlib
from pathlib import Path

from models.schemas import DocumentType, PipelineContext
from utils.logger import log_error, log_layer, log_success, log_warning


def _extract_text_file(path: str) -> str:
    """Read a plain text / markdown file."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _decode_pdf_literal_string(data: bytes) -> str:
    """Decode a PDF literal string from inside parentheses."""
    out = bytearray()
    i = 0
    while i < len(data):
        ch = data[i]
        if ch == 92:  # backslash
            i += 1
            if i >= len(data):
                break
            esc = data[i]
            if esc in (ord("n"), ord("r"), ord("t"), ord("b"), ord("f")):
                mapping = {
                    ord("n"): b"\n",
                    ord("r"): b"\r",
                    ord("t"): b"\t",
                    ord("b"): b"\b",
                    ord("f"): b"\f",
                }
                out.extend(mapping[esc])
            elif esc == ord("("):
                out.append(ord("("))
            elif esc == ord(")"):
                out.append(ord(")"))
            elif esc == ord("\\"):
                out.append(ord("\\"))
            elif esc in (10, 13):
                while i + 1 < len(data) and data[i + 1] in (10, 13):
                    i += 1
            elif 48 <= esc <= 55:
                octal = bytes([esc])
                for _ in range(2):
                    if i + 1 < len(data) and 48 <= data[i + 1] <= 55:
                        i += 1
                        octal += bytes([data[i]])
                    else:
                        break
                out.append(int(octal, 8))
            else:
                out.append(esc)
        else:
            out.append(ch)
        i += 1

    return out.decode("utf-8", errors="replace").replace("\x00", "").strip()


def _decode_hex_pdf_string(hex_data: bytes) -> str:
    hex_text = hex_data.replace(b" ", b"")
    if len(hex_text) % 2 != 0 or not hex_text:
        return ""
    try:
        raw = bytes.fromhex(hex_text.decode("ascii"))
    except ValueError:
        return ""
    return raw.decode("utf-8", errors="replace").strip("\x00").strip()


def _decode_pdf_array_content(array_content: bytes) -> str:
    """Decode a TJ array into one readable text fragment."""
    parts: list[str] = []
    piece_re = re.compile(br"\(((?:\\.|[^\\()])*)\)|([-+]?\d+(?:\.\d+)?)", re.DOTALL)

    for piece in piece_re.finditer(array_content):
        text_piece, numeric_piece = piece.groups()
        if text_piece is not None:
            text = _decode_pdf_literal_string(text_piece)
            if text:
                parts.append(text)
        elif numeric_piece is not None:
            try:
                adjustment = float(numeric_piece)
            except ValueError:
                continue
            if abs(adjustment) >= 100:
                parts.append(" ")

    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _extract_pdf_strings(pdf_bytes: bytes) -> list[str]:
    """Extract text from decompressed PDF content streams."""
    results: list[str] = []

    stream_re = re.compile(br"<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
    op_re = re.compile(
        br"\[(.*?)\]\s*TJ|<([0-9A-Fa-f\s]+)>\s*Tj|\(((?:\\.|[^\\()])*)\)\s*Tj",
        re.DOTALL,
    )

    for stream_match in stream_re.finditer(pdf_bytes):
        header = stream_match.group(1)
        stream = stream_match.group(2)

        if b"/FlateDecode" in header:
            try:
                stream = zlib.decompress(stream)
            except Exception:
                # If decompression fails, keep the raw bytes and continue.
                pass

        for match in op_re.finditer(stream):
            array_content, hex_content, literal_content = match.groups()
            text = ""
            if array_content is not None:
                text = _decode_pdf_array_content(array_content)
            elif hex_content is not None:
                text = _decode_hex_pdf_string(hex_content)
            elif literal_content is not None:
                text = _decode_pdf_literal_string(literal_content)

            if text:
                results.append(text)

    if not results:
        # Fallback for very simple PDFs or malformed demo files.
        for literal in re.finditer(br"\(((?:\\.|[^\\()])*)\)", pdf_bytes, re.DOTALL):
            text = _decode_pdf_literal_string(literal.group(1))
            if text:
                results.append(text)

    return results


def _extract_pdf(path: str) -> str:
    """
    Extract text from a PDF.

    Uses PyMuPDF when installed, otherwise falls back to a small pure-Python
    text parser that works well for simple text-based PDFs.
    """
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None

    if fitz is not None:
        try:
            doc = fitz.open(path)
            pages = []
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text")
                if text.strip():
                    pages.append(f"--- Page {page_num} ---\n{text.strip()}")
            doc.close()
            if pages:
                return "\n\n".join(pages)
        except Exception:
            # Fall back to the pure-Python parser below.
            pass

    pdf_bytes = Path(path).read_bytes()
    extracted = _extract_pdf_strings(pdf_bytes)
    if not extracted:
        raise ValueError("PDF contains no extractable text. May be image-only; use OCR.")
    return "\n".join(extracted)


def _extract_image(_path: str) -> str:
    """
    Stub for image/scanned document OCR.
    Future: call pytesseract or Claude Vision API here.
    """
    raise NotImplementedError(
        "Image OCR is not yet implemented. "
        "Future plan: integrate pytesseract or Claude Vision API."
    )


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 2 entry point.
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

        if len(raw_text.strip()) < 50:
            log_warning("Extracted text is suspiciously short - may be low quality")

        ctx.raw_text = raw_text.strip()
        log_success(f"Extracted {len(ctx.raw_text):,} characters of text")

    except (NotImplementedError, ValueError, ImportError) as exc:
        log_error(f"Text extraction failed: {exc}")
        raise

    return ctx
