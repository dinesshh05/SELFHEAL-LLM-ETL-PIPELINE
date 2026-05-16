from __future__ import annotations

import hashlib
import os
from pathlib import Path

from models.schemas import DocumentType, PipelineContext
from utils.logger import log_error, log_layer, log_success


_EXT_MAP: dict[str, DocumentType] = {
    ".txt": DocumentType.TEXT,
    ".md": DocumentType.TEXT,
    ".pdf": DocumentType.PDF,
}


def run(file_path: str) -> PipelineContext:
    """
    Entry point for Layer 1.
    """
    log_layer("INGESTION", f"Receiving file -> {file_path}")

    path = Path(file_path).resolve()

    if not path.exists():
        log_error(f"File not found: {path}")
        raise FileNotFoundError(f"No file at path: {path}")

    if path.stat().st_size == 0:
        log_error("File is empty - nothing to process")
        raise ValueError(f"File is empty: {path}")

    suffix = path.suffix.lower()
    document_type = _EXT_MAP.get(suffix, DocumentType.UNKNOWN)

    if document_type == DocumentType.UNKNOWN:
        log_error(f"Unsupported file extension: '{suffix}'")
        raise ValueError(
            f"Unsupported file type '{suffix}'. Supported: {list(_EXT_MAP.keys())}"
        )

    log_success(
        f"File accepted | type={document_type.value} | size={os.path.getsize(path):,} bytes"
    )

    ctx = PipelineContext(
        source_file=str(path),
        document_type=document_type,
        source_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
    )

    return ctx
