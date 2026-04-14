"""
layers/layer8_storage.py
─────────────────────────
LAYER 8 — Storage Layer

Tech Stack:
  • SQLAlchemy 2.x  — ORM, session management, relationships
  • SQLite (default) — swap DATABASE_URL for PostgreSQL/MySQL in production

Responsibility:
  Persist the candidate master record plus all related child records
  (skills, education, experience) in a single transaction.
  Stores ctx.db_record_id on success.

  Stores REGARDLESS of status — FAILED records are stored too so you can
  audit what went wrong, query retry counts, and feed a review queue.
"""

from __future__ import annotations

import json
import os

from models.db_models import (
    CandidateRecord,
    EducationRecord,
    ExperienceRecord,
    SkillRecord,
    init_db,
)
from models.schemas import PipelineContext
from utils.logger import log_error, log_layer, log_success


# ─────────────────────────────────────────────
# DB session (module-level singleton)
# ─────────────────────────────────────────────

_DB_URL = os.environ.get("DATABASE_URL", "sqlite:///./pipeline.db")
_session = None


def _get_session():
    global _session
    if _session is None:
        _session = init_db(_DB_URL)
    return _session


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 8 entry point.

    Persists ctx data to the relational database.
    Populates ctx.db_record_id with the inserted primary key.
    """
    log_layer("STORAGE", f"Persisting record — status={ctx.status.value}")

    session = _get_session()

    try:
        vd = ctx.validated_data

        # ── Master candidate record ──────────
        record = CandidateRecord(
            source_file       = ctx.source_file,
            name              = vd.name              if vd else None,
            email             = str(vd.email)        if vd else None,
            phone             = vd.phone             if vd else None,
            confidence_score  = vd.confidence_score  if vd else None,
            status            = ctx.status.value,
            retry_count       = ctx.retry_count,
            raw_llm_response  = ctx.raw_llm_response,
        )
        record.set_healing_log(ctx.healing_log)

        session.add(record)
        session.flush()          # get PK before committing children

        # ── Child records (only if validated) ─
        if vd:
            for skill_str in vd.skills:
                session.add(SkillRecord(candidate_id=record.id, skill=skill_str))

            for edu in vd.education:
                session.add(EducationRecord(
                    candidate_id    = record.id,
                    degree          = edu.degree,
                    institution     = edu.institution,
                    graduation_year = edu.graduation_year,
                ))

            for exp in vd.experience:
                session.add(ExperienceRecord(
                    candidate_id   = record.id,
                    company        = exp.company,
                    role           = exp.role,
                    duration_years = exp.duration_years,
                ))

        session.commit()
        ctx.db_record_id = record.id

        log_success(
            f"Saved to DB │ id={record.id} │ "
            f"status={record.status} │ "
            + (f"name={record.name}" if record.name else "name=N/A")
        )

    except Exception as exc:
        session.rollback()
        log_error(f"DB write failed: {exc}")
        raise

    return ctx
