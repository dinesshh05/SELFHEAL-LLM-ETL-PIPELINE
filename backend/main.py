from __future__ import annotations

import csv
import io
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import sessionmaker

from models.db_models import CandidateRecord, prepare_database
from pipeline import run_pipeline_context
from utils.llm_runtime import resolve_llm_mode


def create_app(database_url: str | None = None, upload_dir: str | None = None) -> FastAPI:
    db_url = database_url or os.environ.get("DATABASE_URL", "sqlite:///./pipeline.db")
    uploads_path = Path(upload_dir or os.environ.get("UPLOAD_DIR", "runtime_uploads")).resolve()
    uploads_path.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = db_url
    os.environ["UPLOAD_DIR"] = str(uploads_path)

    engine = prepare_database(db_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    app = FastAPI(title="Self-Healing ETL Demo", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.database_url = db_url
    app.state.uploads_path = uploads_path
    app.state.session_local = SessionLocal

    class FolderProcessRequest(BaseModel):
        folder_path: str

    def _session():
        return SessionLocal()

    def _record_summary(record: CandidateRecord) -> dict:
        return {
            "id": record.id,
            "name": record.name,
            "email": record.email,
            "status": record.status,
            "document_type": record.document_type,
            "llm_mode": record.llm_mode,
            "confidence_score": record.confidence_score,
            "retry_count": record.retry_count,
            "processing_ms": record.processing_ms,
            "source_file": record.source_file,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    def _record_detail(record: CandidateRecord) -> dict:
        return {
            **_record_summary(record),
            "source_hash": record.source_hash,
            "raw_text": record.raw_text,
            "raw_llm_response": record.raw_llm_response,
            "parsed_data": record.get_parsed_data(),
            "validation_errors": record.get_validation_errors(),
            "healing_log": record.get_healing_log(),
            "phone": record.phone,
        }

    def _filtered_query(
        session,
        *,
        status: str | None = None,
        q: str | None = None,
        llm_mode: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
    ):
        query = session.query(CandidateRecord)

        if status:
            query = query.filter(CandidateRecord.status == status)

        if llm_mode:
            query = query.filter(CandidateRecord.llm_mode == llm_mode)

        if min_confidence is not None:
            query = query.filter(CandidateRecord.confidence_score >= min_confidence)

        if max_confidence is not None:
            query = query.filter(CandidateRecord.confidence_score <= max_confidence)

        if q:
            pattern = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    CandidateRecord.name.ilike(pattern),
                    CandidateRecord.email.ilike(pattern),
                    CandidateRecord.source_file.ilike(pattern),
                    CandidateRecord.document_type.ilike(pattern),
                )
            )

        return query

    def _serialize_export_row(record: CandidateRecord) -> dict:
        row = _record_detail(record)
        row["validation_errors"] = json.dumps(row["validation_errors"])
        row["healing_log"] = json.dumps(row["healing_log"])
        row["parsed_data"] = json.dumps(row["parsed_data"], ensure_ascii=False)
        return row

    def _save_upload(file: UploadFile, destination_dir: Path) -> Path:
        source_name = Path(file.filename or "upload.txt").name
        suffix = Path(source_name).suffix.lower() or ".txt"
        destination = destination_dir / f"{uuid4().hex}{suffix}"
        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return destination

    def _safe_llm_mode() -> str:
        try:
            return resolve_llm_mode()
        except Exception as exc:
            return f"error: {exc}"

    def _run_document(file_path: Path) -> dict:
        try:
            ctx = run_pipeline_context(str(file_path))
            return {
                "record_id": ctx.db_record_id,
                "status": ctx.status.value,
                "llm_mode": ctx.llm_mode,
                "processing_ms": ctx.processing_ms,
                "source_file": ctx.source_file,
                "source_hash": ctx.source_hash,
                "validation_errors": ctx.validation_errors,
                "healing_log": ctx.healing_log,
            }
        except Exception as exc:
            return {
                "record_id": None,
                "status": "FAILED",
                "llm_mode": _safe_llm_mode(),
                "processing_ms": None,
                "source_file": str(file_path),
                "source_hash": None,
                "validation_errors": [str(exc)],
                "healing_log": [f"Pipeline error - {exc}"],
            }

    def _dashboard_html() -> str:
        return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Self-Healing ETL Demo</title>
  <style>
    :root {
      --bg: #f5efe6;
      --bg-2: #eef2ee;
      --panel: rgba(255, 250, 242, 0.88);
      --panel-2: rgba(243, 237, 228, 0.95);
      --border: rgba(55, 65, 81, 0.14);
      --text: #1f2937;
      --muted: #6b7280;
      --accent: #1f6f5b;
      --accent-2: #c46a2b;
      --good: #1f8a5b;
      --warn: #c47d1f;
      --bad: #d14b4b;
      --shadow: 0 22px 60px rgba(31, 41, 55, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 8% 12%, rgba(31, 111, 91, 0.12), transparent 18%),
        radial-gradient(circle at 90% 10%, rgba(196, 106, 43, 0.14), transparent 20%),
        radial-gradient(circle at 50% 100%, rgba(31, 111, 91, 0.09), transparent 24%),
        linear-gradient(180deg, var(--bg) 0%, var(--bg-2) 100%);
      min-height: 100vh;
      position: relative;
      overflow-x: hidden;
    }
    body::before,
    body::after {
      content: "";
      position: fixed;
      inset: auto;
      pointer-events: none;
      border-radius: 999px;
      filter: blur(18px);
      opacity: 0.45;
      z-index: 0;
    }
    body::before {
      width: 240px;
      height: 240px;
      top: 48px;
      right: -64px;
      background: radial-gradient(circle, rgba(196, 106, 43, 0.22), rgba(196, 106, 43, 0));
    }
    body::after {
      width: 300px;
      height: 300px;
      left: -88px;
      bottom: -92px;
      background: radial-gradient(circle, rgba(31, 111, 91, 0.2), rgba(31, 111, 91, 0));
    }
    .wrap {
      max-width: 1240px;
      margin: 0 auto;
      padding: 28px 18px 40px;
      position: relative;
      z-index: 1;
    }
    .hero {
      display: grid;
      grid-template-columns: 1.3fr 0.8fr;
      gap: 18px;
      align-items: stretch;
      margin-bottom: 18px;
    }
    .brand, .stats, .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
    }
    .brand {
      padding: 30px;
      border-left: 6px solid var(--accent);
      position: relative;
      overflow: hidden;
    }
    .brand::after {
      content: "";
      position: absolute;
      inset: auto -60px -88px auto;
      width: 220px;
      height: 220px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(31, 111, 91, 0.12), rgba(31, 111, 91, 0));
      pointer-events: none;
    }
    .brand h1 {
      margin: 0 0 14px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(2.2rem, 5vw, 4rem);
      line-height: 0.98;
      letter-spacing: -0.03em;
      max-width: 12ch;
    }
    .brand p {
      margin: 0;
      color: var(--muted);
      max-width: 62ch;
      font-size: 1rem;
      line-height: 1.72;
    }
    .badge {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 8px 12px; border-radius: 999px;
      background: rgba(31, 111, 91, 0.12);
      color: var(--accent);
      border: 1px solid rgba(31, 111, 91, 0.18);
      margin-bottom: 16px;
      font-size: 0.85rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
    }
    .stats {
      padding: 18px;
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .stat {
      padding: 18px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(243, 237, 228, 0.96));
      border: 1px solid var(--border);
    }
    .stat .label { color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.08em; }
    .stat .value { margin-top: 8px; font-size: 1.9rem; font-weight: 800; letter-spacing: -0.03em; }
    .grid {
      display: grid;
      grid-template-columns: 0.95fr 1.05fr;
      gap: 18px;
      align-items: start;
    }
    .panel {
      padding: 20px;
      position: relative;
      overflow: hidden;
    }
    .panel::before {
      content: "";
      position: absolute;
      inset: 0 0 auto 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(31, 111, 91, 0.22), transparent);
    }
    .panel h2 {
      margin: 0 0 14px;
      font-size: 1.08rem;
      letter-spacing: -0.02em;
    }
    label { display: block; margin-bottom: 8px; color: var(--muted); font-size: 0.9rem; }
    input[type="file"] {
      width: 100%;
      padding: 12px;
      background: rgba(255, 255, 255, 0.82);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 14px;
      margin-bottom: 10px;
    }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .filters {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin: 14px 0 18px;
      padding: 14px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.55);
      border: 1px solid var(--border);
    }
    .filters .full { grid-column: 1 / -1; }
    input[type="text"], input[type="number"], select {
      width: 100%;
      padding: 12px;
      background: rgba(255, 255, 255, 0.88);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 14px;
      outline: none;
    }
    button {
      appearance: none;
      border: none;
      border-radius: 14px;
      padding: 12px 16px;
      cursor: pointer;
      font-weight: 800;
      background: linear-gradient(135deg, var(--accent), #154d40);
      color: #f8fafc;
      box-shadow: 0 10px 24px rgba(31, 111, 91, 0.2);
    }
    button.secondary {
      background: rgba(255, 255, 255, 0.7);
      color: var(--text);
      border: 1px solid var(--border);
      box-shadow: none;
    }
    button:hover {
      transform: translateY(-1px);
      filter: saturate(1.05);
    }
    .hint { margin-top: 10px; color: var(--muted); font-size: 0.9rem; line-height: 1.55; }
    .table {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 14px;
    }
    .table th, .table td {
      text-align: left;
      padding: 12px 10px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.12);
      vertical-align: top;
      font-size: 0.92rem;
    }
    .table th { color: var(--muted); font-weight: 700; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .pill {
      display: inline-flex;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .pill.good { background: rgba(34, 197, 94, 0.14); color: #86efac; }
    .pill.warn { background: rgba(245, 158, 11, 0.16); color: #fcd34d; }
    .pill.bad { background: rgba(239, 68, 68, 0.16); color: #fca5a5; }
    .details {
      margin-top: 18px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      background: #f8f5ee;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      max-height: 320px;
      overflow: auto;
      color: #1f2937;
    }
    .muted { color: var(--muted); }
    @media (max-width: 960px) {
      .hero, .grid, .details, .filters { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <section class="brand">
        <div class="badge">Portfolio Dashboard</div>
        <h1>A resume pipeline with a clean audit trail.</h1>
        <p>
          Upload a resume, see the 9-layer pipeline run, inspect validation and repair attempts,
          and review the structured candidate record in a refined dashboard that feels ready to present.
        </p>
      </section>
      <aside class="stats" id="stats">
        <div class="stat"><div class="label">Total runs</div><div class="value" id="total-count">0</div></div>
        <div class="stat"><div class="label">Processed</div><div class="value" id="processed-count">0</div></div>
        <div class="stat"><div class="label">Pending review</div><div class="value" id="pending-count">0</div></div>
        <div class="stat"><div class="label">Failed</div><div class="value" id="failed-count">0</div></div>
      </aside>
    </div>

    <div class="grid">
      <section class="panel">
        <h2>Process a resume</h2>
        <form id="upload-form">
          <label for="file">Choose one resume or a folder of resumes</label>
          <input id="file" name="file" type="file" accept=".txt,.pdf,.md" multiple webkitdirectory directory required />
          <div class="row">
            <button type="submit">Run pipeline</button>
            <button type="button" id="batch-btn">Run batch</button>
            <button type="button" class="secondary" id="reload-btn">Refresh data</button>
          </div>
        </form>
        <div class="hint" id="status-message">
          Demo mode is automatic when no Groq key is configured, so the project still works in interviews.
        </div>
      </section>

      <section class="panel">
        <h2>Recent runs</h2>
        <div class="filters">
          <div class="full">
            <label for="search-query">Search by name, email, file, or document type</label>
            <input id="search-query" type="text" placeholder="Search records..." />
          </div>
          <div>
            <label for="status-filter">Status</label>
            <select id="status-filter">
              <option value="">All statuses</option>
              <option value="PROCESSED">Processed</option>
              <option value="PENDING_REVIEW">Pending review</option>
              <option value="FAILED">Failed</option>
            </select>
          </div>
          <div>
            <label for="mode-filter">LLM mode</label>
            <select id="mode-filter">
              <option value="">Any mode</option>
              <option value="mock">Mock</option>
              <option value="groq">Groq</option>
              <option value="auto">Auto</option>
            </select>
          </div>
          <div>
            <label for="min-confidence">Min confidence</label>
            <input id="min-confidence" type="number" step="0.01" min="0" max="1" placeholder="0.50" />
          </div>
          <div>
            <label for="max-confidence">Max confidence</label>
            <input id="max-confidence" type="number" step="0.01" min="0" max="1" placeholder="1.00" />
          </div>
          <div class="full row">
            <button type="button" class="secondary" id="filter-btn">Apply filters</button>
            <button type="button" class="secondary" id="reset-btn">Reset</button>
            <button type="button" class="secondary" id="export-csv-btn">Export CSV</button>
            <button type="button" class="secondary" id="export-json-btn">Export JSON</button>
          </div>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>ID</th><th>Name</th><th>Status</th><th>Mode</th><th>Score</th><th>Runtime</th>
            </tr>
          </thead>
          <tbody id="records-body">
            <tr><td colspan="6" class="muted">Loading records...</td></tr>
          </tbody>
        </table>
        <div class="details">
          <div>
            <h2>Validation / Healing</h2>
            <pre id="healing-view">Select a record to inspect validation errors and healing attempts.</pre>
          </div>
          <div>
            <h2>Structured output</h2>
            <pre id="output-view">The parsed JSON for the selected record will appear here.</pre>
          </div>
        </div>
      </section>
    </div>
  </div>

  <script>
    const statusMessage = document.getElementById("status-message");
    const recordsBody = document.getElementById("records-body");
    const healingView = document.getElementById("healing-view");
    const outputView = document.getElementById("output-view");
    const fileInput = document.getElementById("file");
    const searchQuery = document.getElementById("search-query");
    const statusFilter = document.getElementById("status-filter");
    const modeFilter = document.getElementById("mode-filter");
    const minConfidence = document.getElementById("min-confidence");
    const maxConfidence = document.getElementById("max-confidence");

    function statusClass(status) {
      if (status === "PROCESSED") return "good";
      if (status === "PENDING_REVIEW") return "warn";
      return "bad";
    }

    function fmt(value) {
      return value === null || value === undefined || value === "" ? "—" : value;
    }

    function collectFilters() {
      const params = new URLSearchParams();
      if (searchQuery.value.trim()) params.set("q", searchQuery.value.trim());
      if (statusFilter.value) params.set("status", statusFilter.value);
      if (modeFilter.value) params.set("llm_mode", modeFilter.value);
      if (minConfidence.value) params.set("min_confidence", minConfidence.value);
      if (maxConfidence.value) params.set("max_confidence", maxConfidence.value);
      return params;
    }

    async function loadStats() {
      const response = await fetch("/api/report");
      const data = await response.json();
      document.getElementById("total-count").textContent = data.total;
      document.getElementById("processed-count").textContent = data.processed;
      document.getElementById("pending-count").textContent = data.pending;
      document.getElementById("failed-count").textContent = data.failed;
    }

    async function loadRecords(filters = collectFilters()) {
      const params = new URLSearchParams(filters);
      params.set("limit", "12");
      const response = await fetch(`/api/records?${params.toString()}`);
      const data = await response.json();
      recordsBody.innerHTML = "";

      if (!data.items.length) {
        recordsBody.innerHTML = '<tr><td colspan="6" class="muted">No records yet. Upload a file to create the first run.</td></tr>';
        return;
      }

      data.items.forEach((record) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${record.id}</td>
          <td>${fmt(record.name)}</td>
          <td><span class="pill ${statusClass(record.status)}">${record.status}</span></td>
          <td>${fmt(record.llm_mode)}</td>
          <td>${fmt(record.confidence_score !== null ? record.confidence_score.toFixed(2) : null)}</td>
          <td>${fmt(record.processing_ms)} ms</td>
        `;
        row.style.cursor = "pointer";
        row.addEventListener("click", () => loadRecord(record.id));
        recordsBody.appendChild(row);
      });
    }

    async function loadRecord(id) {
      const response = await fetch(`/api/records/${id}`);
      const record = await response.json();
      healingView.textContent = JSON.stringify(
        {
          validation_errors: record.validation_errors,
          healing_log: record.healing_log,
          raw_llm_preview: (record.raw_llm_response || "").slice(0, 1000)
        },
        null,
        2
      );
      outputView.textContent = JSON.stringify(record.parsed_data || {}, null, 2);
    }

    document.getElementById("upload-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!fileInput.files.length) return;

      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      statusMessage.textContent = "Processing... this usually takes a few seconds.";

      const response = await fetch("/api/process", { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) {
        statusMessage.textContent = `Upload failed: ${result.detail || "unknown error"}`;
        return;
      }

      statusMessage.textContent = `Saved record ${result.record_id} with status ${result.status}.`;
      await loadStats();
      await loadRecords();
      if (result.record_id) {
        await loadRecord(result.record_id);
      }
    });

    document.getElementById("batch-btn").addEventListener("click", async () => {
      if (!fileInput.files.length) return;

      const formData = new FormData();
      Array.from(fileInput.files).forEach((file) => formData.append("files", file));
      statusMessage.textContent = "Running batch processing...";

      const response = await fetch("/api/batch", { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) {
        statusMessage.textContent = `Batch failed: ${result.detail || "unknown error"}`;
        return;
      }

      statusMessage.textContent = `Batch complete: ${result.summary.processed} processed, ${result.summary.pending} pending, ${result.summary.failed} failed.`;
      await loadStats();
      await loadRecords();
      const firstRecord = result.items.find((item) => item.record_id);
      if (firstRecord) {
        await loadRecord(firstRecord.record_id);
      }
    });

    document.getElementById("reload-btn").addEventListener("click", async () => {
      await loadStats();
      await loadRecords();
    });

    document.getElementById("filter-btn").addEventListener("click", async () => {
      await loadRecords();
    });

    document.getElementById("reset-btn").addEventListener("click", async () => {
      searchQuery.value = "";
      statusFilter.value = "";
      modeFilter.value = "";
      minConfidence.value = "";
      maxConfidence.value = "";
      await loadRecords();
    });

    function triggerExport(format) {
      const params = collectFilters();
      params.set("format", format);
      window.location.href = `/api/export?${params.toString()}`;
    }

    document.getElementById("export-csv-btn").addEventListener("click", () => triggerExport("csv"));
    document.getElementById("export-json-btn").addEventListener("click", () => triggerExport("json"));

    loadStats();
    loadRecords();
  </script>
</body>
</html>"""

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return _dashboard_html()

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "database_url": db_url,
            "upload_dir": str(uploads_path),
            "llm_mode": _safe_llm_mode(),
        }

    @app.post("/api/process")
    async def process(file: UploadFile = File(...)) -> dict:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Upload must include a filename")

        try:
            destination = _save_upload(file, uploads_path)
            result = _run_document(destination)
        finally:
            await file.close()

        return result

    @app.post("/api/batch")
    async def batch(files: list[UploadFile] = File(...)) -> dict:
        if not files:
            raise HTTPException(status_code=400, detail="At least one file is required")

        items: list[dict] = []
        for upload in files:
            if not upload.filename:
                items.append(
                    {
                        "record_id": None,
                        "status": "FAILED",
                        "source_file": None,
                        "validation_errors": ["Missing filename"],
                        "healing_log": [],
                    }
                )
                continue

            try:
                destination = _save_upload(upload, uploads_path)
                items.append(_run_document(destination))
            finally:
                await upload.close()

        summary = {
            "total": len(items),
            "processed": sum(1 for item in items if item["status"] == "PROCESSED"),
            "pending": sum(1 for item in items if item["status"] == "PENDING_REVIEW"),
            "failed": sum(1 for item in items if item["status"] == "FAILED"),
        }
        return {"summary": summary, "items": items}

    @app.post("/api/process-folder")
    def process_folder(payload: FolderProcessRequest) -> dict:
        folder = Path(payload.folder_path).expanduser().resolve()
        if not folder.exists() or not folder.is_dir():
            raise HTTPException(status_code=400, detail="folder_path must point to an existing directory")

        from pipeline import run_pipeline_batch  # local import avoids cycles during app startup

        contexts = run_pipeline_batch(str(folder))
        items = [
            {
                "record_id": ctx.db_record_id,
                "status": ctx.status.value,
                "llm_mode": ctx.llm_mode,
                "processing_ms": ctx.processing_ms,
                "source_file": ctx.source_file,
                "source_hash": ctx.source_hash,
                "validation_errors": ctx.validation_errors,
                "healing_log": ctx.healing_log,
            }
            for ctx in contexts
        ]

        return {
            "summary": {
                "total": len(items),
                "processed": sum(1 for item in items if item["status"] == "PROCESSED"),
                "pending": sum(1 for item in items if item["status"] == "PENDING_REVIEW"),
                "failed": sum(1 for item in items if item["status"] == "FAILED"),
            },
            "items": items,
        }

    @app.get("/api/records")
    def records(
        limit: int = 20,
        status: str | None = None,
        q: str | None = None,
        llm_mode: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
    ) -> dict:
        session = _session()
        try:
            query = _filtered_query(
                session,
                status=status,
                q=q,
                llm_mode=llm_mode,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
            )
            total = query.count()
            rows = query.order_by(CandidateRecord.id.desc()).limit(limit).all()
            return {
                "items": [_record_summary(record) for record in rows],
                "count": total,
                "filters": {
                    "limit": limit,
                    "status": status,
                    "q": q,
                    "llm_mode": llm_mode,
                    "min_confidence": min_confidence,
                    "max_confidence": max_confidence,
                },
            }
        finally:
            session.close()

    @app.get("/api/report")
    def report() -> dict:
        session = _session()
        try:
            total = session.query(CandidateRecord).count()
            processed = session.query(CandidateRecord).filter(CandidateRecord.status == "PROCESSED").count()
            pending = session.query(CandidateRecord).filter(CandidateRecord.status == "PENDING_REVIEW").count()
            failed = session.query(CandidateRecord).filter(CandidateRecord.status == "FAILED").count()
            avg_runtime = session.query(func.avg(CandidateRecord.processing_ms)).scalar() or 0

            return {
                "total": total,
                "processed": processed,
                "pending": pending,
                "failed": failed,
                "avg_runtime_ms": round(float(avg_runtime), 2),
            }
        finally:
            session.close()

    @app.get("/api/export")
    def export_records(
        format: str = "csv",
        status: str | None = None,
        q: str | None = None,
        llm_mode: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
    ):
        session = _session()
        try:
            records = (
                _filtered_query(
                    session,
                    status=status,
                    q=q,
                    llm_mode=llm_mode,
                    min_confidence=min_confidence,
                    max_confidence=max_confidence,
                )
                .order_by(CandidateRecord.id.desc())
                .all()
            )

            if format.lower() == "json":
                return JSONResponse(
                    content={
                        "items": [_record_detail(record) for record in records],
                        "count": len(records),
                    }
                )

            if format.lower() != "csv":
                raise HTTPException(status_code=400, detail="format must be csv or json")

            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "id",
                    "name",
                    "email",
                    "status",
                    "document_type",
                    "llm_mode",
                    "confidence_score",
                    "retry_count",
                    "processing_ms",
                    "source_file",
                    "source_hash",
                    "created_at",
                    "validation_errors",
                    "healing_log",
                    "parsed_data",
                ],
            )
            writer.writeheader()
            for record in records:
                row = _serialize_export_row(record)
                writer.writerow(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "email": row["email"],
                        "status": row["status"],
                        "document_type": row["document_type"],
                        "llm_mode": row["llm_mode"],
                        "confidence_score": row["confidence_score"],
                        "retry_count": row["retry_count"],
                        "processing_ms": row["processing_ms"],
                        "source_file": row["source_file"],
                        "source_hash": row["source_hash"],
                        "created_at": row["created_at"],
                        "validation_errors": row["validation_errors"],
                        "healing_log": row["healing_log"],
                        "parsed_data": row["parsed_data"],
                    }
                )

            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="records.csv"'},
            )
        finally:
            session.close()

    return app


app = create_app()
