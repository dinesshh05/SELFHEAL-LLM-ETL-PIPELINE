from __future__ import annotations

import os

from models.schemas import PipelineContext, ProcessingStatus
from utils.logger import log_info, log_layer, log_success, log_warning


HIGH_CONFIDENCE = float(os.environ.get("HIGH_CONFIDENCE_THRESHOLD", 0.80))
LOW_CONFIDENCE = float(os.environ.get("LOW_CONFIDENCE_THRESHOLD", 0.50))


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 7 entry point.
    Sets ctx.status to one of: PROCESSED | PENDING_REVIEW | FAILED.
    """
    log_layer(
        "CONFIDENCE ROUTING",
        f"Thresholds: HIGH>={HIGH_CONFIDENCE:.0%}  LOW>={LOW_CONFIDENCE:.0%}",
    )

    if ctx.validation_errors or ctx.validated_data is None:
        ctx.status = ProcessingStatus.FAILED
        log_warning("Record routed -> FAILED (validation errors present)")
        return ctx

    score = ctx.validated_data.confidence_score
    log_info(f"Confidence score: {score:.2f}")

    if score >= HIGH_CONFIDENCE:
        ctx.status = ProcessingStatus.PROCESSED
        log_success(f"Record routed -> PROCESSED (score {score:.2f} >= {HIGH_CONFIDENCE:.2f})")

    elif score >= LOW_CONFIDENCE:
        ctx.status = ProcessingStatus.PENDING_REVIEW
        log_warning(
            f"Record routed -> PENDING_REVIEW "
            f"(score {score:.2f} is between {LOW_CONFIDENCE:.2f} and {HIGH_CONFIDENCE:.2f})"
        )

    else:
        ctx.status = ProcessingStatus.FAILED
        log_warning(f"Record routed -> FAILED (score {score:.2f} < {LOW_CONFIDENCE:.2f})")

    return ctx
