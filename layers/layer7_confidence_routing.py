"""
layers/layer7_confidence_routing.py
─────────────────────────────────────
LAYER 7 — Confidence Routing Layer

Tech Stack:
  • Pure Python — no external deps needed
  • Reads thresholds from environment variables

Responsibility:
  Assign a ProcessingStatus to the record based on:
    1. Whether validation passed or failed
    2. The LLM-reported confidence_score

  Routing logic:
    ┌─────────────────────────────────┬──────────────────┐
    │ Condition                       │ Status           │
    ├─────────────────────────────────┼──────────────────┤
    │ Validation failed               │ FAILED           │
    │ confidence_score ≥ HIGH (0.80)  │ PROCESSED        │
    │ confidence_score ≥ LOW  (0.50)  │ PENDING_REVIEW   │
    │ confidence_score < LOW  (0.50)  │ FAILED           │
    └─────────────────────────────────┴──────────────────┘

  Populates ctx.status.
"""

from __future__ import annotations

import os

from models.schemas import PipelineContext, ProcessingStatus
from utils.logger import log_info, log_layer, log_success, log_warning


# ─────────────────────────────────────────────
# Thresholds (configurable via .env)
# ─────────────────────────────────────────────

HIGH_CONFIDENCE = float(os.environ.get("HIGH_CONFIDENCE_THRESHOLD", 0.80))
LOW_CONFIDENCE  = float(os.environ.get("LOW_CONFIDENCE_THRESHOLD",  0.50))


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 7 entry point.

    Sets ctx.status to one of: PROCESSED | PENDING_REVIEW | FAILED.
    """
    log_layer(
        "CONFIDENCE ROUTING",
        f"Thresholds: HIGH≥{HIGH_CONFIDENCE:.0%}  LOW≥{LOW_CONFIDENCE:.0%}",
    )

    # ── Validation gate ──────────────────────
    if ctx.validation_errors or ctx.validated_data is None:
        ctx.status = ProcessingStatus.FAILED
        log_warning("Record routed → FAILED (validation errors present)")
        return ctx

    score = ctx.validated_data.confidence_score
    log_info(f"Confidence score: {score:.2f}")

    # ── Route by score ───────────────────────
    if score >= HIGH_CONFIDENCE:
        ctx.status = ProcessingStatus.PROCESSED
        log_success(f"Record routed → PROCESSED  (score {score:.2f} ≥ {HIGH_CONFIDENCE:.2f})")

    elif score >= LOW_CONFIDENCE:
        ctx.status = ProcessingStatus.PENDING_REVIEW
        log_warning(
            f"Record routed → PENDING_REVIEW  "
            f"(score {score:.2f} is between {LOW_CONFIDENCE:.2f} and {HIGH_CONFIDENCE:.2f})"
        )

    else:
        ctx.status = ProcessingStatus.FAILED
        log_warning(f"Record routed → FAILED  (score {score:.2f} < {LOW_CONFIDENCE:.2f})")

    return ctx
