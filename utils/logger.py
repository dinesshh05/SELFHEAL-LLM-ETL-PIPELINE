"""
utils/logger.py
────────────────
Centralised Rich logger for all pipeline layers.
Tech: Rich (beautiful console output with color + structure)
"""

from rich.console import Console
from rich.theme import Theme

_theme = Theme({
    "layer":   "bold cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error":   "bold red",
    "heal":    "bold magenta",
    "info":    "dim white",
})

console = Console(theme=_theme)


def log_layer(layer_name: str, message: str) -> None:
    console.print(f"[layer]▶ [{layer_name}][/layer]  {message}")


def log_success(message: str) -> None:
    console.print(f"[success]✔  {message}[/success]")


def log_warning(message: str) -> None:
    console.print(f"[warning]⚠  {message}[/warning]")


def log_error(message: str) -> None:
    console.print(f"[error]✘  {message}[/error]")


def log_heal(message: str) -> None:
    console.print(f"[heal]🔧 SELF-HEAL │ {message}[/heal]")


def log_info(message: str) -> None:
    console.print(f"[info]   {message}[/info]")
