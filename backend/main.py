from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import func
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

    def _dashboard_html() -> str:
        return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Self-Healing ETL Demo</title>
  <style>
    :root {
      --bg: #0b1120;
      --panel: rgba(15, 23, 42, 0.82);
      --panel-2: rgba(30, 41, 59, 0.82);
      --border: rgba(148, 163, 184, 0.18);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #14b8a6;
      --accent-2: #f59e0b;
      --good: #22c55e;
      --warn: #f59e0b;
      --bad: #ef4444;
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.32);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(20, 184, 166, 0.22), transparent 28%),
        radial-gradient(circle at top right, rgba(245, 158, 11, 0.18), transparent 22%),
        linear-gradient(160deg, #020617, var(--bg) 45%, #111827);
      min-height: 100vh;
    }
    .wrap { max-width: 1240px; margin: 0 auto; padding: 28px 18px 40px; }
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
      border-radius: 20px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }
    .brand { padding: 28px; }
    .brand h1 { margin: 0 0 10px; font-size: clamp(2rem, 5vw, 3.6rem); line-height: 1.02; }
    .brand p { margin: 0; color: var(--muted); max-width: 60ch; font-size: 1rem; line-height: 1.65; }
    .badge {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 8px 12px; border-radius: 999px;
      background: rgba(20, 184, 166, 0.14); color: #99f6e4;
      border: 1px solid rgba(20, 184, 166, 0.25); margin-bottom: 16px;
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
      border-radius: 16px;
      background: var(--panel-2);
      border: 1px solid var(--border);
    }
    .stat .label { color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.06em; }
    .stat .value { margin-top: 8px; font-size: 1.8rem; font-weight: 800; }
    .grid {
      display: grid;
      grid-template-columns: 0.95fr 1.05fr;
      gap: 18px;
      align-items: start;
    }
    .panel { padding: 20px; }
    .panel h2 { margin: 0 0 14px; font-size: 1.15rem; }
    label { display: block; margin-bottom: 8px; color: var(--muted); font-size: 0.9rem; }
    input[type="file"] {
      width: 100%;
      padding: 12px;
      background: rgba(15, 23, 42, 0.9);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 14px;
      margin-bottom: 10px;
    }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    button {
      appearance: none;
      border: none;
      border-radius: 14px;
      padding: 12px 16px;
      cursor: pointer;
      font-weight: 800;
      background: linear-gradient(135deg, var(--accent), #0f766e);
      color: #02110f;
      box-shadow: 0 10px 30px rgba(20, 184, 166, 0.22);
    }
    button.secondary {
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
      box-shadow: none;
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
    .table th { color: var(--muted); font-weight: 700; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }
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
      background: rgba(2, 6, 23, 0.88);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      max-height: 320px;
      overflow: auto;
      color: #dbeafe;
    }
    .muted { color: var(--muted); }
    @media (max-width: 960px) {
      .hero, .grid, .details { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <section class="brand">
        <div class="badge">Self-Healing ETL Demo</div>
        <h1>Resume parsing that can explain, repair, and store its own work.</h1>
        <p>
          Upload a resume, see the 9-layer pipeline run, inspect validation and repair attempts,
          and review the structured candidate record in a clean dashboard.
        </p>
      </section>
      <aside class="stats" id="stats">
        <div class="stat"><div class="label">Total</div><div class="value" id="total-count">0</div></div>
        <div class="stat"><div class="label">Processed</div><div class="value" id="processed-count">0</div></div>
        <div class="stat"><div class="label">Pending</div><div class="value" id="pending-count">0</div></div>
        <div class="stat"><div class="label">Failed</div><div class="value" id="failed-count">0</div></div>
      </aside>
    </div>

    <div class="grid">
      <section class="panel">
        <h2>Process a resume</h2>
        <form id="upload-form">
          <label for="file">Choose a .txt or .pdf resume</label>
          <input id="file" name="file" type="file" accept=".txt,.pdf,.md" required />
          <div class="row">
            <button type="submit">Run pipeline</button>
            <button type="button" class="secondary" id="reload-btn">Refresh data</button>
          </div>
        </form>
        <div class="hint" id="status-message">
          Demo mode is automatic when no Groq key is configured, so the project still works in interviews.
        </div>
      </section>

      <section class="panel">
        <h2>Recent runs</h2>
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

    function statusClass(status) {
      if (status === "PROCESSED") return "good";
      if (status === "PENDING_REVIEW") return "warn";
      return "bad";
    }

    function fmt(value) {
      return value === null || value === undefined || value === "" ? "—" : value;
    }

    async function loadStats() {
      const response = await fetch("/api/report");
      const data = await response.json();
      document.getElementById("total-count").textContent = data.total;
      document.getElementById("processed-count").textContent = data.processed;
      document.getElementById("pending-count").textContent = data.pending;
      document.getElementById("failed-count").textContent = data.failed;
    }

    async function loadRecords() {
      const response = await fetch("/api/records?limit=12");
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
      const fileInput = document.getElementById("file");
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
      await loadRecord(result.record_id);
    });

    document.getElementById("reload-btn").addEventListener("click", async () => {
      await loadStats();
      await loadRecords();
    });

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
        try:
            llm_mode = resolve_llm_mode()
        except Exception as exc:
            llm_mode = f"error: {exc}"
        return {
            "status": "ok",
            "database_url": db_url,
            "upload_dir": str(uploads_path),
            "llm_mode": llm_mode,
        }

    @app.post("/api/process")
    async def process(file: UploadFile = File(...)) -> dict:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Upload must include a filename")

        source_name = Path(file.filename).name
        suffix = Path(source_name).suffix.lower() or ".txt"
        destination = uploads_path / f"{uuid4().hex}{suffix}"

        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            ctx = run_pipeline_context(str(destination))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            await file.close()

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

    @app.get("/api/records")
    def records(limit: int = 20) -> dict:
        session = _session()
        try:
            rows = session.query(CandidateRecord).order_by(CandidateRecord.id.desc()).limit(limit).all()
            return {"items": [_record_summary(record) for record in rows]}
        finally:
            session.close()

    @app.get("/api/records/{record_id}")
    def record_detail(record_id: int) -> dict:
        session = _session()
        try:
            record = session.get(CandidateRecord, record_id)
            if not record:
                raise HTTPException(status_code=404, detail="Record not found")
            return _record_detail(record)
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

    return app


app = create_app()
