"""
layers/layer9_monitoring.py
────────────────────────────
LAYER 9 — Monitoring / Review Layer

Tech Stack:
  • SQLAlchemy 2.x  — query DB for aggregate stats
  • Rich             — pretty console tables and panels

MVP Mode:
  Prints a live summary to the console after each run, and a full
  pipeline report when called in report mode.

Future extensions:
  • Expose /metrics endpoint (FastAPI + Prometheus)
  • Slack / email alerts on FAILED spikes
  • Human review web UI (FastAPI + HTMX)
  • Audit trail export (CSV / Parquet)
"""

from __future__ import annotations

import os

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from models.db_models import CandidateRecord, init_db
from models.schemas import PipelineContext, ProcessingStatus
from utils.logger import log_layer

console = Console()

_DB_URL = os.environ.get("DATABASE_URL", "sqlite:///./pipeline.db")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_session():
    return init_db(_DB_URL)


def _count_status(session, status: str) -> int:
    return (
        session.query(CandidateRecord)
        .filter(CandidateRecord.status == status)
        .count()
    )


# ─────────────────────────────────────────────
# Per-run summary (called after every pipeline run)
# ─────────────────────────────────────────────

def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 9 entry point — called after every document run.
    Prints a Rich panel summarising this record's outcome.
    """
    log_layer("MONITORING", "Recording pipeline outcome…")

    status_color = {
        ProcessingStatus.PROCESSED:      "green",
        ProcessingStatus.PENDING_REVIEW: "yellow",
        ProcessingStatus.FAILED:         "red",
    }.get(ctx.status, "white")

    vd = ctx.validated_data
    lines = [
        f"[bold]File:[/bold]          {ctx.source_file}",
        f"[bold]Status:[/bold]        [{status_color}]{ctx.status.value}[/{status_color}]",
        f"[bold]DB Record ID:[/bold]  {ctx.db_record_id or 'N/A'}",
        f"[bold]Retry count:[/bold]   {ctx.retry_count}",
        f"[bold]Confidence:[/bold]    {vd.confidence_score:.2f}" if vd else "[bold]Confidence:[/bold]    N/A",
        f"[bold]Name:[/bold]          {vd.name}"                 if vd else "[bold]Name:[/bold]          N/A",
        f"[bold]Email:[/bold]         {vd.email}"                if vd else "[bold]Email:[/bold]         N/A",
    ]

    if ctx.healing_log:
        lines.append("")
        lines.append("[bold]Healing log:[/bold]")
        for entry in ctx.healing_log:
            lines.append(f"  • {entry}")

    if ctx.validation_errors:
        lines.append("")
        lines.append("[bold red]Remaining errors:[/bold red]")
        for err in ctx.validation_errors:
            lines.append(f"  [red]✘[/red] {err}")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold cyan]Pipeline Run Summary[/bold cyan]",
            border_style="cyan",
        )
    )

    return ctx


# ─────────────────────────────────────────────
# Full pipeline report (call separately)
# ─────────────────────────────────────────────

def print_full_report() -> None:
    """
    Print an aggregate report of all records in the database.
    Call this from CLI:  python -c "from layers.layer9_monitoring import print_full_report; print_full_report()"
    """
    session = _get_session()

    total      = session.query(CandidateRecord).count()
    processed  = _count_status(session, "PROCESSED")
    pending    = _count_status(session, "PENDING_REVIEW")
    failed     = _count_status(session, "FAILED")

    # Aggregate table
    summary = Table(title="Pipeline Report — All Records", show_header=True, header_style="bold cyan")
    summary.add_column("Metric",   style="dim")
    summary.add_column("Count",    justify="right")
    summary.add_column("Share",    justify="right")

    def pct(n: int) -> str:
        return f"{(n / total * 100):.1f}%" if total else "—"

    summary.add_row("Total records",    str(total),     "100%")
    summary.add_row("✔  Processed",     str(processed), pct(processed))
    summary.add_row("⚠  Pending review",str(pending),   pct(pending))
    summary.add_row("✘  Failed",        str(failed),    pct(failed))

    console.print(summary)

    # Recent records detail table
    recent = session.query(CandidateRecord).order_by(CandidateRecord.id.desc()).limit(20).all()

    detail = Table(title="Recent 20 Records", show_header=True, header_style="bold")
    detail.add_column("ID",       justify="right", style="dim")
    detail.add_column("Name")
    detail.add_column("Email")
    detail.add_column("Status")
    detail.add_column("Retries", justify="right")
    detail.add_column("Score",   justify="right")
    detail.add_column("File",    max_width=30)

    for rec in recent:
        status_style = {
            "PROCESSED":      "green",
            "PENDING_REVIEW": "yellow",
            "FAILED":         "red",
        }.get(rec.status, "white")

        detail.add_row(
            str(rec.id),
            rec.name  or "—",
            rec.email or "—",
            f"[{status_style}]{rec.status}[/{status_style}]",
            str(rec.retry_count),
            f"{rec.confidence_score:.2f}" if rec.confidence_score else "—",
            rec.source_file.split("/")[-1],
        )

    console.print(detail)
