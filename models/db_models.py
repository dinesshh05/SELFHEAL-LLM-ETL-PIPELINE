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
    Integer, String, Text, create_engine, inspect, text,
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
    source_hash      = Column(String(64))
    document_type    = Column(String(32))
    name             = Column(String(256))
    email            = Column(String(256))
    phone            = Column(String(64))
    confidence_score = Column(Float)
    status           = Column(String(32), nullable=False, default="FAILED")
    retry_count      = Column(Integer, default=0)
    raw_text         = Column(Text)
    raw_llm_response = Column(Text)
    parsed_data      = Column(Text)
    validation_errors = Column(Text)
    healing_log      = Column(Text)          # stored as JSON string
    llm_mode         = Column(String(32))
    processing_ms    = Column(Integer)
    created_at       = Column(DateTime, default=datetime.utcnow)

    skills     = relationship("SkillRecord",      back_populates="candidate", cascade="all, delete-orphan")
    education  = relationship("EducationRecord",  back_populates="candidate", cascade="all, delete-orphan")
    experience = relationship("ExperienceRecord", back_populates="candidate", cascade="all, delete-orphan")

    def set_healing_log(self, log: list[str]) -> None:
        self.healing_log = json.dumps(log)

    def get_healing_log(self) -> list[str]:
        return json.loads(self.healing_log) if self.healing_log else []

    def set_validation_errors(self, errors: list[str]) -> None:
        self.validation_errors = json.dumps(errors)

    def get_validation_errors(self) -> list[str]:
        return json.loads(self.validation_errors) if self.validation_errors else []

    def set_parsed_data(self, data: dict | None) -> None:
        self.parsed_data = json.dumps(data) if data is not None else None

    def get_parsed_data(self) -> dict | None:
        return json.loads(self.parsed_data) if self.parsed_data else None


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
    engine = prepare_database(database_url)
    return Session(engine)


def prepare_database(database_url: str):
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    _ensure_legacy_columns(engine)
    return engine


def _ensure_legacy_columns(engine) -> None:
    """Upgrade older SQLite demo databases in place when possible."""
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "candidates" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("candidates")}
    migrations = [
        ("source_hash", "ALTER TABLE candidates ADD COLUMN source_hash VARCHAR(64)"),
        ("document_type", "ALTER TABLE candidates ADD COLUMN document_type VARCHAR(32)"),
        ("raw_text", "ALTER TABLE candidates ADD COLUMN raw_text TEXT"),
        ("parsed_data", "ALTER TABLE candidates ADD COLUMN parsed_data TEXT"),
        ("validation_errors", "ALTER TABLE candidates ADD COLUMN validation_errors TEXT"),
        ("llm_mode", "ALTER TABLE candidates ADD COLUMN llm_mode VARCHAR(32)"),
        ("processing_ms", "ALTER TABLE candidates ADD COLUMN processing_ms INTEGER"),
    ]

    with engine.begin() as connection:
        for column_name, ddl in migrations:
            if column_name not in existing:
                connection.execute(text(ddl))
