from __future__ import annotations

from pydantic import ValidationError  # type: ignore

from models.schemas import CandidateData, PipelineContext
from utils.logger import log_error, log_layer, log_success, log_warning


def _format_errors(exc: ValidationError) -> list[str]:
    """
    Convert a Pydantic ValidationError into a flat list of human-readable strings.
    """
    messages = []
    for error in exc.errors():
        location = " -> ".join(str(loc) for loc in error["loc"])
        msg = error["msg"]
        messages.append(f"Field '{location}' - {msg}")
    return messages


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 5 entry point.
    Validates ctx.parsed_data.
    """
    log_layer("VALIDATION", "Validating extracted data against schema...")

    if not ctx.parsed_data:
        msg = "No parsed data to validate - Layer 4 must succeed first"
        log_error(msg)
        ctx.validation_errors = [msg]
        return ctx

    try:
        candidate = CandidateData(**ctx.parsed_data)
        ctx.validated_data = candidate
        ctx.validation_errors = []
        log_success(
            f"Validation passed | name={candidate.name} | "
            f"confidence={candidate.confidence_score:.2f}"
        )

    except ValidationError as exc:
        errors = _format_errors(exc)
        ctx.validation_errors = errors
        ctx.validated_data = None

        log_warning(f"Validation FAILED - {len(errors)} error(s):")
        for err in errors:
            log_error(f"  -> {err}")

    return ctx
