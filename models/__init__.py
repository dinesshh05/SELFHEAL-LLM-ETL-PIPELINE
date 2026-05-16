"""Shared data models for the pipeline."""

from .db_models import (
    Base,
    CandidateRecord,
    EducationRecord,
    ExperienceRecord,
    SkillRecord,
    init_db,
    prepare_database,
)
from .schemas import (
    CandidateData,
    DocumentType,
    EducationEntry,
    ExperienceEntry,
    PipelineContext,
    ProcessingStatus,
)

__all__ = [
    "Base",
    "CandidateRecord",
    "EducationRecord",
    "ExperienceRecord",
    "SkillRecord",
    "init_db",
    "prepare_database",
    "CandidateData",
    "DocumentType",
    "EducationEntry",
    "ExperienceEntry",
    "PipelineContext",
    "ProcessingStatus",
]
