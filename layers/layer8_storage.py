from __future__ import annotations

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


_session = None
_session_db_url = None


def _get_session():
    global _session, _session_db_url
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./pipeline.db")
    if _session is None or _session_db_url != db_url:
        if _session is not None:
            _session.close()
        _session = init_db(db_url)
        _session_db_url = db_url
    return _session


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 8 entry point.
    Persists ctx data to the relational database.
    """
    log_layer("STORAGE", f"Persisting record - status={ctx.status.value}")

    session = _get_session()

    try:
        vd = ctx.validated_data
        record = CandidateRecord(
            source_file=ctx.source_file,
            source_hash=ctx.source_hash,
            document_type=ctx.document_type.value,
            name=vd.name if vd else None,
            email=str(vd.email) if vd else None,
            phone=vd.phone if vd else None,
            confidence_score=vd.confidence_score if vd else None,
            status=ctx.status.value,
            retry_count=ctx.retry_count,
            raw_text=ctx.raw_text,
            raw_llm_response=ctx.raw_llm_response,
            llm_mode=ctx.llm_mode,
            processing_ms=ctx.processing_ms,
        )
        record.set_healing_log(ctx.healing_log)
        record.set_parsed_data(ctx.parsed_data)
        record.set_validation_errors(ctx.validation_errors)

        session.add(record)
        session.flush()

        if vd:
            for skill_str in vd.skills:
                session.add(SkillRecord(candidate_id=record.id, skill=skill_str))

            for edu in vd.education:
                session.add(
                    EducationRecord(
                        candidate_id=record.id,
                        degree=edu.degree,
                        institution=edu.institution,
                        graduation_year=edu.graduation_year,
                    )
                )

            for exp in vd.experience:
                session.add(
                    ExperienceRecord(
                        candidate_id=record.id,
                        company=exp.company,
                        role=exp.role,
                        duration_years=exp.duration_years,
                    )
                )

        session.commit()
        ctx.db_record_id = record.id

        log_success(
            f"Saved to DB | id={record.id} | status={record.status} | "
            f"name={record.name or 'N/A'}"
        )

    except Exception as exc:
        session.rollback()
        log_error(f"DB write failed: {exc}")
        raise

    return ctx
