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
