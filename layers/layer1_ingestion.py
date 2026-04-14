from __future__ import annotations

import os
from pathlib import Path

from models.schemas import DocumentType, PipelineContext
from utils.logger import log_error, log_layer, log_success


# ─────────────────────────────────────────────
# Type detection map
# ─────────────────────────────────────────────

_EXT_MAP: dict[str, DocumentType] = {
    ".txt":  DocumentType.TEXT,
    ".md":   DocumentType.TEXT,
    ".pdf":  DocumentType.PDF,
}


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def run(file_path: str) -> PipelineContext:
    """
    Entry point for Layer 1.

    Args:
        file_path: Absolute or relative path to the input document.

    Returns:
        A freshly initialised PipelineContext with source_file and
        document_type populated.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError:        If the file is empty.
    """
    log_layer("INGESTION", f"Receiving file → {file_path}")

    path = Path(file_path).resolve()

    # ── Existence check ──────────────────────
    if not path.exists():
        log_error(f"File not found: {path}")
        raise FileNotFoundError(f"No file at path: {path}")

    # ── Empty file guard ─────────────────────
    if path.stat().st_size == 0:
        log_error("File is empty — nothing to process")
        raise ValueError(f"File is empty: {path}")

    # ── Type detection ───────────────────────
    suffix       = path.suffix.lower()
    document_type = _EXT_MAP.get(suffix, DocumentType.UNKNOWN)

    if document_type == DocumentType.UNKNOWN:
        log_error(f"Unsupported file extension: '{suffix}'")
        raise ValueError(
            f"Unsupported file type '{suffix}'. "
            f"Supported: {list(_EXT_MAP.keys())}"
        )

    log_success(
        f"File accepted │ type={document_type.value} │ "
        f"size={os.path.getsize(path):,} bytes"
    )

    # ── Build context ────────────────────────
    ctx = PipelineContext(
        source_file=str(path),
        document_type=document_type,
    )

    return ctx
