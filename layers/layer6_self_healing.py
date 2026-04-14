from __future__ import annotations

import json
import os
import re
import time

from groq import Groq
from pydantic import ValidationError

from models.schemas import CandidateData, PipelineContext
from utils.logger import log_error, log_heal, log_info, log_layer, log_success, log_warning


# Configuration


DEFAULT_MAX_RETRIES = int(os.environ.get("MAX_RETRY_ATTEMPTS", 3))
BASE_BACKOFF_SECONDS = 1.5


# Repair prompt template

REPAIR_PROMPT = """\
You previously extracted structured data from a document, but the output
contains validation errors that must be fixed.

INVALID JSON you produced:
{invalid_json}

VALIDATION ERRORS that were found:
{error_list}

Your task:
- Fix ONLY the fields mentioned in the errors above.
- Keep all other fields exactly as they were.
- Return ONLY the corrected, complete JSON object — no explanation, no markdown.
- Follow these rules strictly:
    • email must be a valid email address
    • confidence_score must be a float between 0.0 and 1.0
    • graduation_year must be an integer between 1950 and 2030 (or null)
    • duration_years must be a non-negative float (or null)
    • skills must be an array of strings
    • phone must have at least 7 digits (or null)

Corrected JSON:
"""

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


# Helpers

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
            f"Field '{' -> '.join(str(l) for l in e['loc'])}' — {e['msg']}"
            for e in exc.errors()
        ]
        return None, errors


# Public API

def run(
    ctx: PipelineContext,
    api_key: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> PipelineContext:
    """
    Layer 6 entry point.

    If ctx.validation_errors is empty → nothing to do, return immediately.
    Otherwise, attempt up to max_retries Groq-assisted repairs.
    """
    log_layer("SELF-HEALING", "Checking for validation errors…")

    # ── Fast path
    if not ctx.validation_errors:
        log_success("No errors found — self-healing layer skipped ✓")
        return ctx

    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        log_warning("GROQ_API_KEY not set — skipping self-healing and keeping validation errors")
        ctx.healing_log.append("Self-healing skipped: GROQ_API_KEY not set")
        return ctx

    model_name = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    client = Groq(api_key=key)

    current_json = ctx.parsed_data or {}
    current_errors = ctx.validation_errors

    for attempt in range(1, max_retries + 1):
        log_heal(f"Repair attempt {attempt}/{max_retries}")
        log_info(f"  Errors to fix: {current_errors}")

        error_list_str = "\n".join(f"  - {e}" for e in current_errors)
        prompt = REPAIR_PROMPT.format(
            invalid_json=json.dumps(current_json, indent=2),
            error_list=error_list_str,
        )

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You return only corrected raw JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            raw_repair = (response.choices[0].message.content or "").strip()
        except Exception as api_exc:
            log_error(f"  API call failed on attempt {attempt}: {api_exc}")
            ctx.healing_log.append(f"Attempt {attempt}: API error — {api_exc}")
            break

        try:
            repaired_dict = _parse_response(raw_repair)
        except (ValueError, json.JSONDecodeError) as parse_exc:
            log_warning(f"  Repair response is not valid JSON: {parse_exc}")
            ctx.healing_log.append(f"Attempt {attempt}: parse failed — {parse_exc}")
            backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            time.sleep(backoff)
            continue

        ctx.retry_count += 1
        validated, new_errors = _validate(repaired_dict)

        ctx.healing_log.append(
            f"Attempt {attempt}: "
            + ("SUCCESS" if not new_errors else f"still {len(new_errors)} error(s)")
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
            log_info(f"  Waiting {backoff:.1f}s before next attempt…")
            time.sleep(backoff)

    log_error(f"Self-healing EXHAUSTED after {max_retries} attempt(s). Record marked FAILED.")
    ctx.validation_errors = current_errors
    return ctx