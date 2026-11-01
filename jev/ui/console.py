"""
Consola visual interactiva para MMAE / JEV estilo Claude Code.
Construida con Rich para proporcionar una experiencia de terminal limpia, ágil,
con bloques de herramientas elegantes, syntax highlighting y cero bloqueos.
"""
from typing import Dict, Any, Optional, List
import json
import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner

from jev.tools.base import ToolResult

console = Console()


def print_banner(model_name: str, workspace_path: str) -> None:
    """Imprime el banner inicial estilo Claude Code."""
    cwd = Path(workspace_path).name or workspace_path
    banner = Text()
    banner.append("╭─────────────────────────────────────────────────────────────────────────────╮\n", style="dim")
    banner.append("│ ", style="dim")
    banner.append("🧠 MMAE Agent ", style="bold bright_cyan")
    banner.append("• Terminal Interface (Claude Code Edition)                      ", style="dim")
    banner.append("│\n", style="dim")
    banner.append("│ ", style="dim")
    banner.append(f"Model: {model_name:<24}", style="bold yellow")
    banner.append(f"Workspace: {cwd:<32}", style="cyan")
    banner.append("│\n", style="dim")
    banner.append("│ ", style="dim")
    banner.append("Escribe tu objetivo en lenguaje natural o ", style="dim")
    banner.append("/help", style="bold green")
    banner.append(" para ver comandos.             ", style="dim")
    banner.append("│\n", style="dim")
    banner.append("╰─────────────────────────────────────────────────────────────────────────────╯", style="dim")
    console.print(banner)


def display_thought(thought_text: str) -> None:
    """Muestra el pensamiento y razonamiento interno de forma concisa y elegante."""
    if not thought_text or not thought_text.strip():
        return
    text = thought_text.strip()
    # Si contiene markdown o es multilínea
    console.print(f"[dim cyan]⏺ {text}[/dim cyan]")


def display_tool_call(tool_name: str, arguments: Dict[str, Any]) -> None:
    """Muestra la invocación de herramientas con estilo de bloque estructurado."""
    header = f"╭── 🛠️  [bold yellow]{tool_name}[/bold yellow] " + "─" * max(10, 58 - len(tool_name))
    console.print(header, style="dim yellow")
    
    # Formatear parámetros con claridad
    if isinstance(arguments, dict):
        for k, v in arguments.items():
            val_str = str(v)
            if len(val_str) > 120 or "\n" in val_str:
                lines_count = len(val_str.splitlines())
                val_str = f"[{lines_count} líneas / {len(val_str)} caracteres]"
            console.print(f"│ [cyan]{k}:[/cyan] [white]{val_str}[/white]", style="dim yellow")
    else:
        console.print(f"│ {arguments}", style="dim yellow")
        
    console.print("╰" + "─" * 65, style="dim yellow")


def display_tool_result(tool_name: str, result: ToolResult) -> None:
    """Muestra el resultado devuelto por una herramienta."""
    if result.success:
        summary = result.output.strip()
        first_line = summary.splitlines()[0] if summary else "Completado exitosamente"
        if len(first_line) > 100:
            first_line = first_line[:100] + "..."
        console.print(f"[bold green]✓[/bold green] [dim]{tool_name}:[/dim] {first_line}")
    else:
        err_msg = (result.error or result.output or "Error desconocido").strip()
        first_err = err_msg.splitlines()[0] if err_msg else "Fallo de ejecución"
        console.print(f"[bold red]✗[/bold red] [red]{tool_name} error:[/red] {first_err[:120]}")


def display_final_answer(answer: str, elapsed_seconds: float = 0.0) -> None:
    """Muestra la respuesta o conclusión final del agente en formato Markdown."""
    console.print()
    md = Markdown(answer)
    console.print(md)
    console.print()
    if elapsed_seconds > 0:
        console.print(f"[dim]⚡ Tarea finalizada en {elapsed_seconds:.2f}s[/dim]\n")


def display_tools_table(tools_list: list) -> None:
    """Muestra una tabla con todas las herramientas disponibles y sus descripciones."""
    table = Table(title="🛠️ Herramientas Disponibles en MMAE", border_style="dim cyan", show_header=True)
    table.add_column("Herramienta", style="bold cyan", width=25)
    table.add_column("Descripción", style="white")

    for tool in tools_list:
        name = getattr(tool, "name", str(tool))
        desc = getattr(tool, "description", "")
        if not desc and hasattr(tool, "__doc__") and tool.__doc__:
            desc = tool.__doc__.strip().splitlines()[0]
        table.add_row(name, (desc[:100] + "...") if len(desc) > 100 else (desc or "Sin descripción"))

    console.print(table)


def ask_terminal_permission(tool_name: str, arguments: Dict[str, Any]) -> bool:
    """Solicita permiso al usuario estilo Claude Code antes de ejecutar una acción sensible."""
    brief = ""
    if isinstance(arguments, dict):
        brief = arguments.get("app") or arguments.get("command") or arguments.get("path") or arguments.get("target") or ""
        if not brief:
            brief = ", ".join(f"{k}={v}" for k, v in list(arguments.items())[:2])
    
    prompt_msg = f"[bold yellow]⚠️  ¿Permitir ejecución de {tool_name} ({brief})? [Y/n]: [/bold yellow]"
    resp = console.input(prompt_msg).strip().lower()
    return resp in ("", "y", "yes", "s", "si")
