"""
Consola visual interactiva para JEV construida con la librería Rich.
Proporciona salida visual formateada, paneles de pensamiento, llamadas a herramientas y estados.
"""
from typing import Dict, Any, Optional
import json
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from rich.table import Table

from jev.tools.base import ToolResult

console = Console()


def print_banner(model_name: str, workspace_path: str) -> None:
    """Imprime el banner inicial de bienvenida de JEV."""
    banner_text = Text()
    banner_text.append("═══════════════════════════════════════════════════════════════\n", style="bold cyan")
    banner_text.append("       🤖 JEV - AGENTE AUTÓNOMO LOCAL (IA AUTOMEJORABLE)       \n", style="bold yellow")
    banner_text.append("═══════════════════════════════════════════════════════════════\n", style="bold cyan")
    banner_text.append(" • Motor Local: ", style="bold")
    banner_text.append(f"{model_name}\n", style="green")
    banner_text.append(" • Espacio de Trabajo: ", style="bold")
    banner_text.append(f"{workspace_path}\n", style="magenta")
    banner_text.append(" • Capacidades: ", style="bold")
    banner_text.append("Pantalla (Computer Use) | Web | Código | Automejora\n", style="blue")
    banner_text.append(" • Parada de Emergencia: ", style="bold")
    banner_text.append("Mover el cursor a la esquina superior izquierda.\n", style="red")
    banner_text.append("═══════════════════════════════════════════════════════════════", style="bold cyan")

    console.print(Panel(banner_text, border_style="cyan", expand=False))


def display_thought(thought_text: str) -> None:
    """Muestra el pensamiento y razonamiento interno del agente."""
    if not thought_text.strip():
        return
    md = Markdown(thought_text)
    console.print(Panel(md, title="🧠 Razonamiento JEV", border_style="cyan", subtitle="Pensamiento interno"))


def display_tool_call(tool_name: str, arguments: Dict[str, Any]) -> None:
    """Muestra la invocación de una herramienta con sus parámetros."""
    args_json = json.dumps(arguments, indent=2, ensure_ascii=False)
    syntax = Syntax(args_json, "json", theme="monokai", line_numbers=False)
    console.print(Panel(
        syntax,
        title=f"⚡ Ejecutando Herramienta: [bold yellow]{tool_name}[/bold yellow]",
        border_style="yellow"
    ))


def display_tool_result(tool_name: str, result: ToolResult) -> None:
    """Muestra el resultado devuelto por una herramienta."""
    if result.success:
        border_color = "green"
        title = f"✓ Resultado: [bold green]{tool_name}[/bold green]"
        content = result.output
    else:
        border_color = "red"
        title = f"✗ Error en: [bold red]{tool_name}[/bold red]"
        content = result.error or result.output

    # Si la salida es muy extensa, dar resumen
    if len(content) > 1500:
        content_preview = content[:1500] + f"\n\n[... truncado: {len(content)} caracteres totales ...]"
    else:
        content_preview = content

    console.print(Panel(content_preview, title=title, border_style=border_color))


def display_final_answer(answer: str) -> None:
    """Muestra la respuesta o conclusión final del agente."""
    md = Markdown(answer)
    console.print(Panel(
        md,
        title="✨ Respuesta Final de JEV",
        border_style="bright_green",
        padding=(1, 2)
    ))


def display_tools_table(tools_list: list) -> None:
    """Muestra una tabla con todas las herramientas disponibles y sus descripciones."""
    table = Table(title="🛠️ Herramientas Disponibles en JEV", border_style="blue")
    table.add_column("Herramienta", style="bold cyan", width=22)
    table.add_column("Descripción", style="white")

    for tool in tools_list:
        table.add_row(tool.name, tool.description[:100] + ("..." if len(tool.description) > 100 else ""))

    console.print(table)
