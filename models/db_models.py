"""
models/db_models.py
────────────────────
SQLAlchemy ORM table definitions.
Tech: SQLAlchemy 2.x with SQLite (swap DATABASE_URL for PostgreSQL in prod)
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────
# ORM Models
# ─────────────────────────────────────────────

class CandidateRecord(Base):
    __tablename__ = "candidates"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    source_file      = Column(String(512), nullable=False)
    name             = Column(String(256))
    email            = Column(String(256))
    phone            = Column(String(64))
    confidence_score = Column(Float)
    status           = Column(String(32), nullable=False, default="FAILED")
    retry_count      = Column(Integer, default=0)
    raw_llm_response = Column(Text)
    healing_log      = Column(Text)          # stored as JSON string
    created_at       = Column(DateTime, default=datetime.utcnow)

    skills     = relationship("SkillRecord",      back_populates="candidate", cascade="all, delete-orphan")
    education  = relationship("EducationRecord",  back_populates="candidate", cascade="all, delete-orphan")
    experience = relationship("ExperienceRecord", back_populates="candidate", cascade="all, delete-orphan")

    def set_healing_log(self, log: list[str]) -> None:
        self.healing_log = json.dumps(log)

    def get_healing_log(self) -> list[str]:
        return json.loads(self.healing_log) if self.healing_log else []


class SkillRecord(Base):
    __tablename__ = "skills"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    skill        = Column(String(256), nullable=False)
    candidate    = relationship("CandidateRecord", back_populates="skills")


class EducationRecord(Base):
    __tablename__ = "education"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id    = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    degree          = Column(String(256))
    institution     = Column(String(256))
    graduation_year = Column(Integer)
    candidate       = relationship("CandidateRecord", back_populates="education")


class ExperienceRecord(Base):
    __tablename__ = "experience"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id   = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    company        = Column(String(256))
    role           = Column(String(256))
    duration_years = Column(Float)
    candidate      = relationship("CandidateRecord", back_populates="experience")


# ─────────────────────────────────────────────
# DB initialisation helper
# ─────────────────────────────────────────────

def init_db(database_url: str) -> Session:
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    return Session(engine)
