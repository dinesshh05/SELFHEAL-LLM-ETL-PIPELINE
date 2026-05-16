from __future__ import annotations

from models.schemas import PipelineContext
from utils.llm_runtime import build_extraction_response
from utils.logger import log_error, log_info, log_layer, log_success


def run(ctx: PipelineContext, api_key: str | None = None) -> PipelineContext:
    """
    Layer 3 entry point.
    Sends ctx.raw_text to the configured LLM runtime and stores the raw
    response string in ctx.raw_llm_response.
    """
    log_layer("LLM EXTRACTION", "Extracting structured data from the document...")

    try:
        response, mode = build_extraction_response(ctx.raw_text or "", api_key=api_key)
    except Exception as exc:
        log_error(f"LLM extraction failed: {exc}")
        raise RuntimeError(f"LLM extraction failed: {exc}") from exc

    ctx.raw_llm_response = response
    ctx.llm_mode = mode

    log_success(f"{mode.upper()} extraction produced {len(response):,} characters")
    preview = response[:120].replace("[", "(").replace("]", ")")
    log_info(f"Preview: {preview}...")

    return ctx
