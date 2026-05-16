# Self-Healing ETL Pipeline

A portfolio-focused ETL project that ingests resumes, extracts structured candidate data, validates the output, repairs bad extractions, routes by confidence, and stores the final result in SQLite.

The main idea is simple: if the LLM returns messy data, the pipeline does not stop. It validates the payload, tries to repair it, and records the full trace so the outcome is explainable.

## What This Project Shows

- Layered ETL design
- LLM-assisted extraction
- Schema validation with Pydantic
- Automatic repair / self-healing
- Confidence-based routing
- SQLAlchemy persistence
- FastAPI backend
- Lightweight dashboard for demos

## Architecture

1. Ingestion checks the file, detects type, and hashes the source.
2. Text extraction reads `.txt`, `.md`, or `.pdf` resumes.
3. LLM extraction produces structured JSON.
4. Structured parsing converts raw output into a Python dict.
5. Validation checks the payload against a strict schema.
6. Self-healing repairs invalid fields and retries.
7. Confidence routing marks the record as `PROCESSED`, `PENDING_REVIEW`, or `FAILED`.
8. Storage writes the full record and trace to SQLite.
9. Monitoring prints a readable run summary and aggregate report.

## Demo Mode

This repo is demo-safe by default. If `LLM_MODE` is not set to `groq`, the pipeline falls back to a deterministic mock runtime, so it still works without an external API key.

That means you can run the project in interviews even if you do not want to expose live LLM credentials.

## Setup

1. Copy `.env.example` to `.env`.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Optional: add a Groq key if you want live extraction.

If you do not add a key, the project will use mock mode automatically.

## Run The CLI

Process one resume:

```bash
python pipeline.py sample_docs/resume.txt
```

Process the self-healing demo sample:

```bash
python pipeline.py sample_docs/resume_heal.txt
```

Print the DB report:

```bash
python pipeline.py --report
```

## Run The API + Dashboard

Start the backend:

```bash
uvicorn backend.main:app --reload
```

Open:

- `http://127.0.0.1:8000/` for the dashboard
- `http://127.0.0.1:8000/docs` for the API docs

## API Endpoints

- `POST /api/process` - upload a resume and run the full pipeline
- `GET /api/records` - list recent runs
- `GET /api/records/{id}` - inspect one run in detail
- `GET /api/report` - aggregate counts
- `GET /health` - service health check

## Example Portfolio Story

You can describe this project as:

> Built a self-healing resume ETL pipeline in Python that extracts candidate data with an LLM, validates and repairs malformed outputs, stores trace data in SQLite, and exposes results through a FastAPI dashboard.

## Tech Stack

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- SQLite
- Rich
- Groq API
- PyMuPDF

## Notes For Interview Demos

- Use `sample_docs/resume_heal.txt` to show self-healing.
- Use the dashboard to show the upload flow and recent runs.
- Use `pipeline.py --report` to show aggregate storage results.
