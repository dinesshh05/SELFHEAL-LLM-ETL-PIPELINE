"""
pipeline.py
Main orchestrator for the 9-layer self-healing pipeline.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

from layers import (  # noqa: E402
    layer1_ingestion,
    layer2_text_extraction,
    layer3_llm_extraction,
    layer4_structured_parsing,
    layer5_validation,
    layer6_self_healing,
    layer7_confidence_routing,
    layer8_storage,
    layer9_monitoring,
)
from models.schemas import PipelineContext, ProcessingStatus  # noqa: E402

console = Console()

LAYER_NAMES = [
    "1 | Ingestion",
    "2 | Text Extraction",
    "3 | LLM Extraction",
    "4 | Structured Parsing",
    "5 | Validation",
    "6 | Self-Healing",
    "7 | Confidence Routing",
    "8 | Storage",
    "9 | Monitoring",
]

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


def _print_banner() -> None:
    console.print("[bold cyan]Self-Healing Pipeline[/bold cyan]")
    console.print("=" * 80)


def _print_step(title: str) -> None:
    console.print(f"[dim]{title}[/dim]")
    console.print("-" * 80)


def _collect_supported_files(root: Path) -> list[Path]:
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files)


def _persist_failure(ctx: PipelineContext, error_message: str, started_at: float) -> PipelineContext:
    ctx.validation_errors = [error_message]
    ctx.status = ProcessingStatus.FAILED
    ctx.processing_ms = int((time.perf_counter() - started_at) * 1000)
    ctx = layer7_confidence_routing.run(ctx)
    ctx = layer8_storage.run(ctx)
    ctx = layer9_monitoring.run(ctx)
    return ctx


def run_pipeline_context(file_path: str) -> PipelineContext:
    """
    Run all 9 layers for a single document and return the full context.
    """
    started_at = time.perf_counter()

    _print_banner()
    console.print(f"[dim]Input: {file_path}[/dim]\n")

    _print_step(LAYER_NAMES[0])
    ctx = layer1_ingestion.run(file_path)

    _print_step(LAYER_NAMES[1])
    ctx = layer2_text_extraction.run(ctx)

    _print_step(LAYER_NAMES[2])
    try:
        ctx = layer3_llm_extraction.run(ctx)
    except Exception as exc:
        console.print(f"[red]LLM extraction failed: {exc}[/red]")
        return _persist_failure(ctx, str(exc), started_at)

    _print_step(LAYER_NAMES[3])
    try:
        ctx = layer4_structured_parsing.run(ctx)
    except ValueError as exc:
        console.print(f"[red]Parsing hard-failed: {exc}[/red]")
        return _persist_failure(ctx, str(exc), started_at)

    _print_step(LAYER_NAMES[4])
    ctx = layer5_validation.run(ctx)

    _print_step(LAYER_NAMES[5])
    ctx = layer6_self_healing.run(ctx)

    _print_step(LAYER_NAMES[6])
    ctx = layer7_confidence_routing.run(ctx)

    ctx.processing_ms = int((time.perf_counter() - started_at) * 1000)

    _print_step(LAYER_NAMES[7])
    ctx = layer8_storage.run(ctx)

    _print_step(LAYER_NAMES[8])
    ctx = layer9_monitoring.run(ctx)

    console.print("=" * 80)
    return ctx


def run_pipeline(file_path: str) -> ProcessingStatus:
    return run_pipeline_context(file_path).status


def run_pipeline_batch(input_path: str, recursive: bool = True) -> list[PipelineContext]:
    root = Path(input_path).resolve()
    if not root.is_dir():
        raise ValueError(f"Batch input must be a directory: {root}")

    files = _collect_supported_files(root) if recursive else [
        path for path in sorted(root.iterdir()) if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not files:
        raise ValueError(f"No supported documents found in {root}")

    console.print("[bold cyan]Batch Mode[/bold cyan]")
    console.print(f"[dim]Folder: {root}[/dim]")
    console.print(f"[dim]Files: {len(files)}[/dim]")
    console.print("=" * 80)

    contexts: list[PipelineContext] = []
    for index, file_path in enumerate(files, start=1):
        console.print(f"[bold]Batch item {index}/{len(files)}[/bold]: {file_path.name}")
        contexts.append(run_pipeline_context(str(file_path)))
        console.print("-" * 80)

    processed = sum(1 for ctx in contexts if ctx.status == ProcessingStatus.PROCESSED)
    pending = sum(1 for ctx in contexts if ctx.status == ProcessingStatus.PENDING_REVIEW)
    failed = sum(1 for ctx in contexts if ctx.status == ProcessingStatus.FAILED)
    console.print(
        f"[bold]Batch summary:[/bold] processed={processed} pending={pending} failed={failed}"
    )
    console.print("=" * 80)
    return contexts


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[red]Usage: python pipeline.py <file_path>[/red]")
        console.print("[red]       python pipeline.py --report[/red]")
        sys.exit(1)

    if sys.argv[1] == "--report":
        layer9_monitoring.print_full_report()
        sys.exit(0)

    input_file = sys.argv[1]

    if not Path(input_file).exists():
        console.print(f"[red]File not found: {input_file}[/red]")
        sys.exit(1)

    target = Path(input_file)
    if target.is_dir():
        contexts = run_pipeline_batch(str(target))
        sys.exit(0 if all(ctx.status != ProcessingStatus.FAILED for ctx in contexts) else 1)

    status = run_pipeline(input_file)
    sys.exit(0 if status != ProcessingStatus.FAILED else 1)
