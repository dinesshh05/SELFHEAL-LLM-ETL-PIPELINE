"""
tests/test_pipeline.py
───────────────────────
Unit tests for individual pipeline layers.
Tech: pytest

Run with:
    pytest tests/ -v
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from models.schemas import (
    CandidateData,
    DocumentType,
    PipelineContext,
    ProcessingStatus,
)


# ─────────────────────────────────────────────
# Layer 1 — Ingestion
# ─────────────────────────────────────────────

class TestLayer1Ingestion:

    def test_valid_text_file(self, tmp_path):
        from layers import layer1_ingestion
        f = tmp_path / "resume.txt"
        f.write_text("Hello World resume content here.")
        ctx = layer1_ingestion.run(str(f))
        assert ctx.document_type == DocumentType.TEXT
        assert ctx.source_file == str(f.resolve())

    def test_valid_pdf_file(self, tmp_path):
        from layers import layer1_ingestion
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 fake content for type detection")
        ctx = layer1_ingestion.run(str(f))
        assert ctx.document_type == DocumentType.PDF

    def test_file_not_found_raises(self):
        from layers import layer1_ingestion
        with pytest.raises(FileNotFoundError):
            layer1_ingestion.run("/nonexistent/path/file.txt")

    def test_empty_file_raises(self, tmp_path):
        from layers import layer1_ingestion
        f = tmp_path / "empty.txt"
        f.write_text("")
        with pytest.raises(ValueError, match="empty"):
            layer1_ingestion.run(str(f))

    def test_unsupported_extension_raises(self, tmp_path):
        from layers import layer1_ingestion
        f = tmp_path / "doc.docx"
        f.write_bytes(b"some content here for testing")
        with pytest.raises(ValueError, match="Unsupported"):
            layer1_ingestion.run(str(f))


# ─────────────────────────────────────────────
# Layer 2 — Text Extraction
# ─────────────────────────────────────────────

class TestLayer2TextExtraction:

    def _make_ctx(self, tmp_path, content: str, filename: str) -> PipelineContext:
        f = tmp_path / filename
        f.write_text(content)
        return PipelineContext(
            source_file=str(f),
            document_type=DocumentType.TEXT,
        )

    def test_extracts_text_file(self, tmp_path):
        from layers import layer2_text_extraction
        ctx = self._make_ctx(tmp_path, "John Doe\nEngineer\nPython, SQL", "r.txt")
        ctx = layer2_text_extraction.run(ctx)
        assert "John Doe" in ctx.raw_text
        assert "Python" in ctx.raw_text

    def test_strips_whitespace(self, tmp_path):
        from layers import layer2_text_extraction
        ctx = self._make_ctx(tmp_path, "   \n  Hello   \n  ", "r.txt")
        ctx = layer2_text_extraction.run(ctx)
        assert ctx.raw_text == "Hello"


# ─────────────────────────────────────────────
# Layer 4 — Structured Parsing
# ─────────────────────────────────────────────

class TestLayer4StructuredParsing:

    def _ctx_with_response(self, response: str) -> PipelineContext:
        return PipelineContext(
            source_file="test.txt",
            document_type=DocumentType.TEXT,
            raw_text="test",
            raw_llm_response=response,
        )

    def test_parses_clean_json(self):
        from layers import layer4_structured_parsing
        raw = json.dumps({"name": "Alice", "email": "a@b.com"})
        ctx = layer4_structured_parsing.run(self._ctx_with_response(raw))
        assert ctx.parsed_data["name"] == "Alice"

    def test_strips_code_fence(self):
        from layers import layer4_structured_parsing
        raw = '```json\n{"name": "Bob", "email": "b@b.com"}\n```'
        ctx = layer4_structured_parsing.run(self._ctx_with_response(raw))
        assert ctx.parsed_data["name"] == "Bob"

    def test_strips_preamble(self):
        from layers import layer4_structured_parsing
        raw = 'Here is the extracted data:\n{"name": "Carol", "email": "c@c.com"}\nHope that helps!'
        ctx = layer4_structured_parsing.run(self._ctx_with_response(raw))
        assert ctx.parsed_data["name"] == "Carol"

    def test_raises_on_no_json(self):
        from layers import layer4_structured_parsing
        with pytest.raises(ValueError):
            layer4_structured_parsing.run(self._ctx_with_response("No JSON here at all."))

    def test_raises_on_malformed_json(self):
        from layers import layer4_structured_parsing
        with pytest.raises(ValueError):
            layer4_structured_parsing.run(self._ctx_with_response('{"name": "Dan", "email":}'))


# ─────────────────────────────────────────────
# Layer 5 — Validation
# ─────────────────────────────────────────────

class TestLayer5Validation:

    def _ctx_with_data(self, data: dict) -> PipelineContext:
        return PipelineContext(
            source_file="test.txt",
            document_type=DocumentType.TEXT,
            raw_text="test",
            parsed_data=data,
        )

    def _valid_payload(self) -> dict:
        return {
            "name": "Alice",
            "email": "alice@example.com",
            "phone": "+91-9876543210",
            "skills": ["Python", "SQL"],
            "education": [{"degree": "B.Tech", "institution": "IIT", "graduation_year": 2020}],
            "experience": [{"company": "Acme", "role": "Engineer", "duration_years": 2.0}],
            "confidence_score": 0.92,
        }

    def test_valid_data_passes(self):
        from layers import layer5_validation
        ctx = layer5_validation.run(self._ctx_with_data(self._valid_payload()))
        assert ctx.validated_data is not None
        assert ctx.validation_errors == []

    def test_invalid_email_fails(self):
        from layers import layer5_validation
        payload = self._valid_payload()
        payload["email"] = "not-an-email"
        ctx = layer5_validation.run(self._ctx_with_data(payload))
        assert len(ctx.validation_errors) > 0
        assert ctx.validated_data is None

    def test_confidence_out_of_range_fails(self):
        from layers import layer5_validation
        payload = self._valid_payload()
        payload["confidence_score"] = 1.5
        ctx = layer5_validation.run(self._ctx_with_data(payload))
        assert len(ctx.validation_errors) > 0

    def test_negative_experience_fails(self):
        from layers import layer5_validation
        payload = self._valid_payload()
        payload["experience"][0]["duration_years"] = -1.0
        ctx = layer5_validation.run(self._ctx_with_data(payload))
        assert len(ctx.validation_errors) > 0

    def test_unrealistic_graduation_year_fails(self):
        from layers import layer5_validation
        payload = self._valid_payload()
        payload["education"][0]["graduation_year"] = 1800
        ctx = layer5_validation.run(self._ctx_with_data(payload))
        assert len(ctx.validation_errors) > 0

    def test_missing_required_name_fails(self):
        from layers import layer5_validation
        payload = self._valid_payload()
        del payload["name"]
        ctx = layer5_validation.run(self._ctx_with_data(payload))
        assert len(ctx.validation_errors) > 0


# ─────────────────────────────────────────────
# Layer 7 — Confidence Routing
# ─────────────────────────────────────────────

class TestLayer7ConfidenceRouting:

    def _ctx_with_score(self, score: float) -> PipelineContext:
        candidate = CandidateData(
            name="Test User",
            email="test@example.com",
            skills=["Python"],
            confidence_score=score,
        )
        ctx = PipelineContext(
            source_file="test.txt",
            document_type=DocumentType.TEXT,
            validated_data=candidate,
        )
        return ctx

    def test_high_confidence_processed(self):
        from layers import layer7_confidence_routing
        ctx = layer7_confidence_routing.run(self._ctx_with_score(0.95))
        assert ctx.status == ProcessingStatus.PROCESSED

    def test_mid_confidence_pending_review(self):
        from layers import layer7_confidence_routing
        ctx = layer7_confidence_routing.run(self._ctx_with_score(0.65))
        assert ctx.status == ProcessingStatus.PENDING_REVIEW

    def test_low_confidence_failed(self):
        from layers import layer7_confidence_routing
        ctx = layer7_confidence_routing.run(self._ctx_with_score(0.30))
        assert ctx.status == ProcessingStatus.FAILED

    def test_validation_errors_force_failed(self):
        from layers import layer7_confidence_routing
        ctx = self._ctx_with_score(0.95)
        ctx.validation_errors = ["Field 'email' — invalid"]
        ctx.validated_data = None
        ctx = layer7_confidence_routing.run(ctx)
        assert ctx.status == ProcessingStatus.FAILED


# ─────────────────────────────────────────────
# Pydantic Schema Tests
# ─────────────────────────────────────────────

class TestCandidateDataSchema:

    def test_valid_candidate_builds(self):
        c = CandidateData(
            name="Bob",
            email="bob@example.com",
            skills=["Go", "Rust"],
            confidence_score=0.88,
        )
        assert c.name == "Bob"

    def test_email_validation(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CandidateData(name="X", email="bad", skills=[], confidence_score=0.5)

    def test_confidence_bounds(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CandidateData(name="X", email="x@x.com", skills=[], confidence_score=1.1)
        with pytest.raises(ValidationError):
            CandidateData(name="X", email="x@x.com", skills=[], confidence_score=-0.1)
