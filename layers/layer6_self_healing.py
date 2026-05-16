from __future__ import annotations

import json
import os
import re
import time

from pydantic import ValidationError

from models.schemas import CandidateData, PipelineContext
from utils.llm_runtime import build_repair_response
from utils.logger import log_error, log_heal, log_info, log_layer, log_success, log_warning


DEFAULT_MAX_RETRIES = int(os.environ.get("MAX_RETRY_ATTEMPTS", 3))
BASE_BACKOFF_SECONDS = 1.5
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_response(raw: str) -> dict:
    fence_match = _CODE_FENCE_RE.search(raw)
    if fence_match:
        raw = fence_match.group(1)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in repair response")
    return json.loads(raw[start : end + 1])


def _validate(data: dict) -> tuple[CandidateData | None, list[str]]:
    try:
        return CandidateData(**data), []
    except ValidationError as exc:
        errors = [
            f"Field '{' -> '.join(str(l) for l in e['loc'])}' - {e['msg']}"
            for e in exc.errors()
        ]
        return None, errors


def run(
    ctx: PipelineContext,
    api_key: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> PipelineContext:
    """
    Layer 6 entry point.

    If ctx.validation_errors is empty, returns immediately.
    Otherwise, attempts up to max_retries repairs using either Groq or the
    deterministic demo-safe mock runtime.
    """
    log_layer("SELF-HEALING", "Checking for validation errors...")

    if not ctx.validation_errors:
        log_success("No errors found - self-healing layer skipped")
        return ctx

    current_json = ctx.parsed_data or {}
    current_errors = ctx.validation_errors

    for attempt in range(1, max_retries + 1):
        log_heal(f"Repair attempt {attempt}/{max_retries}")
        log_info(f"  Errors to fix: {current_errors}")

        try:
            raw_repair, mode = build_repair_response(current_json, current_errors, api_key=api_key)
            ctx.llm_mode = mode
        except Exception as api_exc:
            log_error(f"  Repair runtime failed on attempt {attempt}: {api_exc}")
            ctx.healing_log.append(f"Attempt {attempt}: runtime error - {api_exc}")
            break

        try:
            repaired_dict = _parse_response(raw_repair)
        except (ValueError, json.JSONDecodeError) as parse_exc:
            log_warning(f"  Repair response is not valid JSON: {parse_exc}")
            ctx.healing_log.append(f"Attempt {attempt}: parse failed - {parse_exc}")
            backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            time.sleep(backoff)
            continue

        ctx.retry_count += 1
        validated, new_errors = _validate(repaired_dict)

        ctx.healing_log.append(
            f"Attempt {attempt}: " + ("SUCCESS" if not new_errors else f"still {len(new_errors)} error(s)")
        )

        if not new_errors:
            ctx.parsed_data = repaired_dict
            ctx.validated_data = validated
            ctx.validation_errors = []
            log_success(f"Self-healing SUCCEEDED on attempt {attempt}!")
            return ctx

        log_warning(f"  Still {len(new_errors)} error(s) after repair:")
        for err in new_errors:
            log_info(f"    -> {err}")

        current_json = repaired_dict
        current_errors = new_errors

        if attempt < max_retries:
            backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            log_info(f"  Waiting {backoff:.1f}s before next attempt...")
            time.sleep(backoff)

    log_error(f"Self-healing exhausted after {max_retries} attempt(s). Record marked FAILED.")
    ctx.validation_errors = current_errors
    return ctx
