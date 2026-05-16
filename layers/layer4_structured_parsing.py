

from __future__ import annotations

import json
import re

from models.schemas import PipelineContext
from utils.logger import log_error, log_layer, log_success, log_warning


# ─────────────────────────────────────────────
# Cleaning helpers
# ─────────────────────────────────────────────

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`", re.DOTALL)


def _clean_llm_output(raw: str) -> str:
    """
    Strip common LLM formatting noise to isolate the JSON payload.

    Strategy (in order):
    1. Extract content inside ```json ... ``` or ``` ... ``` fences.
    2. Find the first '{' and last '}' to isolate the JSON object.
    3. Return the cleaned string for json.loads().
    """
    fence_match = _CODE_FENCE_RE.search(raw)
    if fence_match:
        raw = fence_match.group(1)
        log_warning("Stripped markdown code fence from LLM output")

    start = raw.find("{")
    end   = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start : end + 1]
    else:
        raise ValueError("No JSON object found in LLM response")

    return raw.strip()

# Public API

def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 4 entry point.

    Parses ctx.raw_llm_response -> ctx.parsed_data (dict).
    Raises ValueError if JSON cannot be recovered.
    """
    log_layer("STRUCTURED PARSING", "Parsing LLM response into dict...")

    if not ctx.raw_llm_response:
        log_error("No LLM response to parse")
        raise ValueError("ctx.raw_llm_response is empty - Layer 3 must run first")

    try:
        cleaned = _clean_llm_output(ctx.raw_llm_response)
        data    = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log_error(f"JSON parse failed: {exc}")
        log_error(f"Problematic content (first 300 chars): {ctx.raw_llm_response[:300]}")
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object (dict), got {type(data).__name__}")

    ctx.parsed_data = data
    log_success(f"Parsed dict with {len(data)} top-level keys: {list(data.keys())}")

    return ctx
