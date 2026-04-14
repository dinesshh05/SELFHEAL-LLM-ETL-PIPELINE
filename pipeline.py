"""
pipeline.py
────────────
Main orchestrator — connects all 9 layers in sequence.

Usage:
    python pipeline.py path/to/resume.pdf
    python pipeline.py path/to/resume.txt
    python pipeline.py --report          (show full DB report)
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule

load_dotenv()  # load .env before anything else

from layers import (
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
from models.schemas import ProcessingStatus

console = Console()

LAYER_NAMES = [
    "1 · Ingestion",
    "2 · Text Extraction",
    "3 · LLM Extraction",
    "4 · Structured Parsing",
    "5 · Validation",
    "6 · Self-Healing",
    "7 · Confidence Routing",
    "8 · Storage",
    "9 · Monitoring",
]


def run_pipeline(file_path: str) -> ProcessingStatus:
    """
    Run all 9 layers for a single document.
    Returns the final ProcessingStatus.
    """
    console.print(Rule("[bold cyan]Self-Healing Pipeline[/bold cyan]"))
    console.print(f"[dim]Input: {file_path}[/dim]\n")

    # ── Layer 1: Ingestion ───────────────────
    console.print(Rule(LAYER_NAMES[0], style="dim"))
    ctx = layer1_ingestion.run(file_path)

    # ── Layer 2: Text Extraction ─────────────
    console.print(Rule(LAYER_NAMES[1], style="dim"))
    ctx = layer2_text_extraction.run(ctx)

    # ── Layer 3: LLM Extraction ──────────────
    console.print(Rule(LAYER_NAMES[2], style="dim"))
    try:
        ctx = layer3_llm_extraction.run(ctx)
    except Exception as exc:
        console.print(f"[red]LLM extraction failed: {exc}[/red]")
        ctx.validation_errors = [str(exc)]
        ctx = layer7_confidence_routing.run(ctx)
        ctx = layer8_storage.run(ctx)
        ctx = layer9_monitoring.run(ctx)
        return ctx.status

    # ── Layer 4: Structured Parsing ──────────
    console.print(Rule(LAYER_NAMES[3], style="dim"))
    try:
        ctx = layer4_structured_parsing.run(ctx)
    except ValueError as exc:
        console.print(f"[red]Parsing hard-failed: {exc}[/red]")
        ctx.validation_errors = [str(exc)]
        # Skip to storage so we record the failure
        ctx = layer7_confidence_routing.run(ctx)
        ctx = layer8_storage.run(ctx)
        ctx = layer9_monitoring.run(ctx)
        return ctx.status

    # ── Layer 5: Validation ──────────────────
    console.print(Rule(LAYER_NAMES[4], style="dim"))
    ctx = layer5_validation.run(ctx)

    # ── Layer 6: Self-Healing ────────────────
    console.print(Rule(LAYER_NAMES[5], style="dim"))
    ctx = layer6_self_healing.run(ctx)

    # ── Layer 7: Confidence Routing ──────────
    console.print(Rule(LAYER_NAMES[6], style="dim"))
    ctx = layer7_confidence_routing.run(ctx)

    # ── Layer 8: Storage ─────────────────────
    console.print(Rule(LAYER_NAMES[7], style="dim"))
    ctx = layer8_storage.run(ctx)

    # ── Layer 9: Monitoring ──────────────────
    console.print(Rule(LAYER_NAMES[8], style="dim"))
    ctx = layer9_monitoring.run(ctx)

    console.print(Rule(style="dim"))
    return ctx.status


# ─────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────

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

    status = run_pipeline(input_file)

    exit_code = 0 if status == ProcessingStatus.PROCESSED else (
        1 if status == ProcessingStatus.FAILED else 0
    )
    sys.exit(exit_code)
