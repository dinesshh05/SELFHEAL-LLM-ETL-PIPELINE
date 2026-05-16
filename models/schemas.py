"""
models/schemas.py
─────────────────
Central data models shared across all pipeline layers.
Tech: Pydantic v2 for validation + strict typing
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class ProcessingStatus(str, Enum):
    PROCESSED       = "PROCESSED"
    PENDING_REVIEW  = "PENDING_REVIEW"
    FAILED          = "FAILED"


class DocumentType(str, Enum):
    TEXT    = "text"
    PDF     = "pdf"
    IMAGE   = "image"
    UNKNOWN = "unknown"


# ─────────────────────────────────────────────
# Sub-models
# ─────────────────────────────────────────────

class EducationEntry(BaseModel):
    degree:          Optional[str] = None
    institution:     Optional[str] = None
    graduation_year: Optional[int] = None

    @field_validator("graduation_year")
    @classmethod
    def year_must_be_realistic(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1950 <= v <= 2030):
            raise ValueError(f"Graduation year {v} is outside realistic range (1950–2030)")
        return v


class ExperienceEntry(BaseModel):
    company:        Optional[str] = None
    role:           Optional[str] = None
    duration_years: Optional[float] = None

    @field_validator("duration_years")
    @classmethod
    def duration_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("Experience duration cannot be negative")
        return v


# ─────────────────────────────────────────────
# Core extracted candidate schema
# ─────────────────────────────────────────────

class CandidateData(BaseModel):
    name:             str
    email:            EmailStr
    phone:            Optional[str] = None
    skills:           List[str]     = Field(default_factory=list)
    education:        List[EducationEntry] = Field(default_factory=list)
    experience:       List[ExperienceEntry] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)

    @field_validator("phone")
    @classmethod
    def phone_basic_check(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) < 7:
            raise ValueError(f"Phone number '{v}' has too few digits")
        return v

    @field_validator("skills")
    @classmethod
    def skills_must_be_list_of_strings(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("skills must be a list")
        return [str(s) for s in v]


# ─────────────────────────────────────────────
# Pipeline context — flows through all layers
# ─────────────────────────────────────────────

class PipelineContext(BaseModel):
    """Mutable context object passed through every pipeline layer."""

    # Source
    source_file:    str
    document_type:  DocumentType = DocumentType.UNKNOWN
    source_hash:    Optional[str] = None
    raw_text:       Optional[str] = None

    # LLM interaction
    raw_llm_response:   Optional[str]  = None
    parsed_data:        Optional[dict] = None
    validated_data:     Optional[CandidateData] = None
    llm_mode:           str = "auto"

    # Self-healing state
    retry_count:        int = 0
    validation_errors:  List[str] = Field(default_factory=list)
    healing_log:        List[str] = Field(default_factory=list)

    # Routing & output
    status:     ProcessingStatus = ProcessingStatus.FAILED
    db_record_id: Optional[int] = None
    processing_ms: Optional[int] = None
    created_at:   datetime = Field(default_factory=datetime.utcnow)

    model_config = {"arbitrary_types_allowed": True}
