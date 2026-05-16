from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from models.db_models import CandidateRecord, init_db
from models.schemas import PipelineContext, ProcessingStatus
from utils.logger import log_layer

console = Console()


def _get_session():
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./pipeline.db")
    return init_db(db_url)


def _count_status(session, status: str) -> int:
    return session.query(CandidateRecord).filter(CandidateRecord.status == status).count()


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Layer 9 entry point - prints a run summary after persistence.
    """
    log_layer("MONITORING", "Recording pipeline outcome...")

    status_color = {
        ProcessingStatus.PROCESSED: "green",
        ProcessingStatus.PENDING_REVIEW: "yellow",
        ProcessingStatus.FAILED: "red",
    }.get(ctx.status, "white")

    vd = ctx.validated_data
    lines = [
        f"[bold]File:[/bold]          {ctx.source_file}",
        f"[bold]Status:[/bold]        [{status_color}]{ctx.status.value}[/{status_color}]",
        f"[bold]DB Record ID:[/bold]  {ctx.db_record_id or 'N/A'}",
        f"[bold]Runtime mode:[/bold]  {ctx.llm_mode}",
        f"[bold]Duration:[/bold]      {ctx.processing_ms or 'N/A'} ms",
        f"[bold]Retry count:[/bold]   {ctx.retry_count}",
        f"[bold]Confidence:[/bold]    {vd.confidence_score:.2f}" if vd else "[bold]Confidence:[/bold]    N/A",
        f"[bold]Name:[/bold]          {vd.name}" if vd else "[bold]Name:[/bold]          N/A",
        f"[bold]Email:[/bold]         {vd.email}" if vd else "[bold]Email:[/bold]         N/A",
    ]

    if ctx.healing_log:
        lines.append("")
        lines.append("[bold]Healing log:[/bold]")
        for entry in ctx.healing_log:
            lines.append(f"  - {entry}")

    if ctx.validation_errors:
        lines.append("")
        lines.append("[bold red]Remaining errors:[/bold red]")
        for err in ctx.validation_errors:
            lines.append(f"  - {err}")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold cyan]Pipeline Run Summary[/bold cyan]",
            border_style="cyan",
        )
    )

    return ctx


def print_full_report() -> None:
    """
    Print an aggregate report of all records in the database.
    """
    session = _get_session()

    total = session.query(CandidateRecord).count()
    processed = _count_status(session, "PROCESSED")
    pending = _count_status(session, "PENDING_REVIEW")
    failed = _count_status(session, "FAILED")

    summary = Table(title="Pipeline Report - All Records", show_header=True, header_style="bold cyan")
    summary.add_column("Metric", style="dim")
    summary.add_column("Count", justify="right")
    summary.add_column("Share", justify="right")

    def pct(n: int) -> str:
        return f"{(n / total * 100):.1f}%" if total else "-"

    summary.add_row("Total records", str(total), "100%")
    summary.add_row("Processed", str(processed), pct(processed))
    summary.add_row("Pending review", str(pending), pct(pending))
    summary.add_row("Failed", str(failed), pct(failed))

    console.print(summary)

    recent = session.query(CandidateRecord).order_by(CandidateRecord.id.desc()).limit(20).all()

    detail = Table(title="Recent 20 Records", show_header=True, header_style="bold")
    detail.add_column("ID", justify="right", style="dim")
    detail.add_column("Name")
    detail.add_column("Email")
    detail.add_column("Status")
    detail.add_column("Mode")
    detail.add_column("Retries", justify="right")
    detail.add_column("Score", justify="right")
    detail.add_column("Ms", justify="right")
    detail.add_column("File", max_width=30)

    for rec in recent:
        status_style = {
            "PROCESSED": "green",
            "PENDING_REVIEW": "yellow",
            "FAILED": "red",
        }.get(rec.status, "white")

        detail.add_row(
            str(rec.id),
            rec.name or "-",
            rec.email or "-",
            f"[{status_style}]{rec.status}[/{status_style}]",
            rec.llm_mode or "-",
            str(rec.retry_count),
            f"{rec.confidence_score:.2f}" if rec.confidence_score is not None else "-",
            str(rec.processing_ms) if rec.processing_ms is not None else "-",
            Path(rec.source_file).name,
        )

    console.print(detail)
