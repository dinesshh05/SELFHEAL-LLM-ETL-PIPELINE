from __future__ import annotations

import asyncio
import os
from io import BytesIO
from pathlib import Path

from starlette.datastructures import UploadFile


def _sample_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "sample_docs" / name


def _route(app, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route.endpoint
    raise AssertionError(f"Route not found: {path}")


def _make_simple_pdf(lines: list[str]) -> bytes:
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_parts = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        if index:
            content_parts.append("0 -18 Td")
        content_parts.append(f"({escape(line)}) Tj")
    content_parts.append("ET")
    stream = "\n".join(content_parts).encode("utf-8")

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        b"4 0 obj << /Length "
        + str(len(stream)).encode("ascii")
        + b" >> stream\n"
        + stream
        + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]

    offsets = [0]
    position = len(header)
    for obj in objects:
        offsets.append(position)
        position += len(obj)

    xref_start = position
    xref_entries = [b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref_entries.append(f"{offset:010d} 00000 n \n".encode("ascii"))

    xref = b"xref\n0 6\n" + b"".join(xref_entries)
    trailer = f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii")
    return header + b"".join(objects) + xref + trailer


def test_api_process_self_heals_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pipeline.db'}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    from backend.main import create_app

    app = create_app(
        database_url=os.environ["DATABASE_URL"],
        upload_dir=os.environ["UPLOAD_DIR"],
    )

    process = _route(app, "/api/process")
    records = _route(app, "/api/records")
    record_detail = _route(app, "/api/records/{record_id}")
    report = _route(app, "/api/report")

    sample_file = _sample_path("resume_heal.txt")
    upload = UploadFile(filename=sample_file.name, file=BytesIO(sample_file.read_bytes()))
    payload = asyncio.run(process(file=upload))

    assert payload["status"] == "PROCESSED"
    assert payload["record_id"] is not None
    assert payload["validation_errors"] == []

    record_id = payload["record_id"]
    detail = record_detail(record_id=record_id)
    assert detail["status"] == "PROCESSED"
    assert detail["validation_errors"] == []
    assert detail["healing_log"]
    assert detail["parsed_data"]["name"] == "Aanya Sharma"

    summary = report()
    assert summary["total"] == 1
    assert summary["processed"] == 1
    assert summary["failed"] == 0

    listing = records(limit=10)
    assert listing["items"][0]["id"] == record_id


def test_batch_search_and_export(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pipeline.db'}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    from backend.main import create_app

    app = create_app(
        database_url=os.environ["DATABASE_URL"],
        upload_dir=os.environ["UPLOAD_DIR"],
    )

    batch = _route(app, "/api/batch")
    records = _route(app, "/api/records")
    export = _route(app, "/api/export")

    files = [
        UploadFile(filename="resume.txt", file=BytesIO(_sample_path("resume.txt").read_bytes())),
        UploadFile(filename="resume_heal.txt", file=BytesIO(_sample_path("resume_heal.txt").read_bytes())),
    ]
    result = asyncio.run(batch(files=files))

    assert result["summary"]["total"] == 2
    assert result["summary"]["processed"] == 2

    filtered = records(limit=10, status="PROCESSED", q="John")
    assert filtered["count"] >= 1
    assert any(item["name"] == "John Doe" for item in filtered["items"])

    csv_response = export(format="csv", status="PROCESSED")
    csv_text = csv_response.body.decode("utf-8")
    assert "name,email,status" in csv_text
    assert "John Doe" in csv_text

    json_response = export(format="json", q="Aanya")
    json_text = json_response.body.decode("utf-8")
    assert "\"items\"" in json_text
    assert "Aanya Sharma" in json_text


def test_dashboard_serves_html(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pipeline.db'}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    from backend.main import create_app

    app = create_app(
        database_url=os.environ["DATABASE_URL"],
        upload_dir=os.environ["UPLOAD_DIR"],
    )

    dashboard = _route(app, "/")
    html = dashboard()
    assert "Self-Healing ETL Demo" in html
    assert "Export CSV" in html


def test_api_process_pdf_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pipeline.db'}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    from backend.main import create_app

    app = create_app(
        database_url=os.environ["DATABASE_URL"],
        upload_dir=os.environ["UPLOAD_DIR"],
    )

    process = _route(app, "/api/process")
    records = _route(app, "/api/records")

    pdf_path = tmp_path / "resume.pdf"
    pdf_bytes = _make_simple_pdf(
        [
            "John Doe",
            "Email: john.doe@example.com",
            "Phone: +91 9876543210",
            "Skills: Python, SQL, Machine Learning, Pandas",
            "Education: B.Tech in Computer Science, ABC Institute, 2023",
            "Experience: Data Analyst Intern at XYZ Pvt Ltd, 1.5 years",
        ]
    )
    pdf_path.write_bytes(pdf_bytes)

    upload = UploadFile(filename=pdf_path.name, file=BytesIO(pdf_path.read_bytes()))
    payload = asyncio.run(process(file=upload))

    assert payload["status"] == "PROCESSED"
    assert payload["record_id"] is not None
    assert payload["validation_errors"] == []

    listing = records(limit=10, q="John", status="PROCESSED")
    assert listing["count"] >= 1
    assert any(item["name"] == "John Doe" for item in listing["items"])
