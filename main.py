"""
Punto de entrada principal para MMAE (Macro-Micro Agent Engine) y JEV.
Terminal interactiva estilo Claude Code (CLI nativo de alto rendimiento).
"""
import sys
import os
import time
import argparse
from pathlib import Path
from typing import Optional

# Asegurar codificación UTF-8 en Windows para caracteres especiales y emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Autodescubrimiento del entorno virtual local para máxima portabilidad
_base_dir = Path(__file__).resolve().parent
_venv_site = _base_dir / ".venv" / "Lib" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.insert(0, str(_venv_site))
if str(_base_dir) not in sys.path:
    sys.path.insert(0, str(_base_dir))

from config import config, default_config, AgentConfig
from core.agent import MMAEAutonomousAgent, AgentCore
from core.evaluator import OutputEvaluator
from jev.core.status_sync import set_agent_status

try:
    from jev.ui.console import (
        console,
        print_banner,
        display_thought,
        display_tool_call,
        display_tool_result,
        display_final_answer,
        display_tools_table,
        ask_terminal_permission,
    )
except Exception:
    console = None
    ask_terminal_permission = None


def run_interactive_session(agent_config: AgentConfig) -> None:
    """Inicia la sesión de terminal interactiva estilo Claude Code."""
    if console and print_banner:
        print_banner(model_name=agent_config.model_name, workspace_path=str(agent_config.workspace_dir))
    else:
        print(f"=== MMAE Agent • Claude Code CLI ({agent_config.model_name}) ===")
        print("Escribe tu objetivo o '/help' para ver comandos.\n")

    def _on_thought_handler(t: str):
        set_agent_status(state="thinking", thought=str(t)[:160], running=True)
        if console:
            display_thought(t)
        else:
            print(f"[Pensamiento] {t}")

    # Callback de permisos para acciones sensibles en la terminal
    def _on_tool_call_handler(name: str, args: dict):
        set_agent_status(state="tool", tool=name, tool_args=str(args)[:140], tool_in_progress=True, running=True)
        if console:
            display_tool_call(name, args)
        else:
            print(f"[Acción] {name}: {args}")

        # Si el modo seguro está activo o es una acción de escritorio/sistema
        if agent_config.confirm_risky_actions or name in ("desktop_app_live_type", "desktop_live_operator", "keyboard_type", "mouse_click"):
            if ask_terminal_permission:
                return ask_terminal_permission(name, args)
        return True

    def _on_tool_result_handler(name: str, result):
        ok = getattr(result, "success", True) if hasattr(result, "success") else True
        set_agent_status(state="tool", tool=name, last_ok=ok, tool_in_progress=False, running=True)
        if console:
            display_tool_result(name, result)
        else:
            print(f"[Resultado] {name}")

    agent = AgentCore(
        config=agent_config,
        on_thought=_on_thought_handler,
        on_tool_call=_on_tool_call_handler,
        on_tool_result=_on_tool_result_handler
    ) if AgentCore else None

    while True:
        try:
            prompt_str = "❯ "
            if console and sys.stdin.isatty():
                raw_input = console.input(f"[bold bright_green]{prompt_str}[/bold bright_green]")
            else:
                if console:
                    console.print(f"[bold bright_green]{prompt_str}[/bold bright_green]", end="")
                raw_input = input()

            # Sanitizar posibles secuencias de escape ANSI, BOM UTF-8 de PowerShell o comillas de pipe
            import re
            cleaned = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(raw_input or "")).strip().lstrip('\ufeff').strip("'\"")
            if not cleaned:
                continue

            user_input = cleaned
            cmd_lower = user_input.lower()

            # Comandos especiales
            if cmd_lower in ("/exit", "exit", "quit", ":q", "/q", "salir"):
                if console:
                    console.print("\n[dim]Hasta pronto. Sesión de MMAE finalizada.[/dim]\n")
                else:
                    print("\nHasta pronto. Sesión finalizada.\n")
                break

            if cmd_lower in ("/clear", "clear", "cls"):
                if console:
                    console.clear()
                    print_banner(model_name=agent_config.model_name, workspace_path=str(agent_config.workspace_dir))
                else:
                    os.system("cls" if sys.platform == "win32" else "clear")
                continue

            if cmd_lower in ("/help", "help", "/?"):
                if console:
                    console.print("\n[bold cyan]📖 Comandos Disponibles estilo Claude Code:[/bold cyan]")
                    console.print(" • [bold green]/tools[/bold green]     : Muestra la tabla de todas las herramientas disponibles")
                    console.print(" • [bold green]/clear[/bold green]     : Limpia la pantalla de la terminal")
                    console.print(" • [bold green]/model <m>[/bold green] : Cambia el modelo activo (ej: /model gemini-2.5-flash)")
                    console.print(" • [bold green]/lessons[/bold green]   : Muestra las lecciones aprendidas de la memoria")
                    console.print(" • [bold green]/desktop[/bold green]   : Abre la Isla flotante de escritorio (Coucou Notch)")
                    console.print(" • [bold green]/exit[/bold green]      : Finaliza la sesión")
                    console.print("\n[dim]Cualquier otra frase se procesará como una tarea autónoma.[/dim]\n")
                continue

            if cmd_lower == "/tools":
                if agent and console:
                    display_tools_table(agent.registry.list_tools())
                continue

            if cmd_lower.startswith("/model"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1 and parts[1].strip():
                    new_model = parts[1].strip()
                    agent_config.model_name = new_model
                    if agent and hasattr(agent, "llm"):
                        agent.llm.model = new_model
                    if console:
                        console.print(f"[bold green]✓ Modelo actualizado a:[/bold green] {new_model}\n")
                else:
                    if console:
                        console.print(f"[dim]Modelo actual: {agent_config.model_name}[/dim]\n")
                continue

            if cmd_lower == "/desktop":
                import subprocess
                subprocess.Popen([sys.executable, "jev_desktop.py"], shell=False)
                if console:
                    console.print("[bold cyan]🚀 Isla flotante de escritorio iniciada en segundo plano.[/bold cyan]\n")
                continue

            if cmd_lower == "/lessons" and agent and console:
                lessons = agent.memory.get_all_lessons() if hasattr(agent.memory, "get_all_lessons") else []
                if not lessons:
                    console.print("[dim]Aún no hay lecciones aprendidas registradas.[/dim]\n")
                else:
                    console.print("\n[bold cyan]📚 Lecciones Aprendidas (Memoria):[/bold cyan]")
                    for item in lessons:
                        console.print(f" • [[bold yellow]{item.get('category')}[/bold yellow]]: {item.get('rule')}")
                    console.print()
                continue

            # Ejecutar con el agente autónomo
            start_time = time.time()
            set_agent_status(state="thinking", task=user_input, running=True, thought="Iniciando tarea...")
            try:
                if agent:
                    result = agent.run_task(user_goal=user_input)
                    elapsed = time.time() - start_time
                    if console:
                        display_final_answer(result, elapsed_seconds=elapsed)
                    else:
                        print(f"\n[Respuesta] ({elapsed:.2f}s):\n{result}\n")
                else:
                    mmae = MMAEAutonomousAgent(agent_config)
                    result = mmae.run(user_input)
                    elapsed = time.time() - start_time
                    if console:
                        display_final_answer(str(result), elapsed_seconds=elapsed)
                    else:
                        print(f"\n[Respuesta] ({elapsed:.2f}s):\n{result}\n")
            finally:
                set_agent_status(state="idle", thought="Completado", running=False, last_ok=True)

        except (KeyboardInterrupt, EOFError):
            if console:
                console.print("\n[dim]Sesión de terminal finalizada.[/dim]\n")
            else:
                print("\nSesión finalizada.")
            break
        except Exception as e:
            if console:
                console.print(f"\n[bold red]Error:[/bold red] {e}\n")
            else:
                print(f"\nError: {e}\n")


def main():
    parser = argparse.ArgumentParser(description="MMAE Agent - Terminal Interface (Claude Code Edition)")
    parser.add_argument("goal", nargs="?", default=None, help="Objetivo para ejecutar en modo autónomo")
    parser.add_argument("--task", type=str, default=None, help="Objetivo o tarea específica")
    parser.add_argument("--model", type=str, default=None, help="Nombre del modelo LLM")
    parser.add_argument("--provider", type=str, default=None, help="Proveedor LLM (ollama, lmstudio, gemini, openrouter)")
    parser.add_argument("--safe-mode", action="store_true", help="Solicitar confirmación antes de ejecutar acciones sensibles")
    parser.add_argument("--desktop", action="store_true", help="Lanzar la Isla flotante de escritorio")
    parser.add_argument("--interactive", "-i", action="store_true", help="Forzar modo consola interactiva")

    args = parser.parse_args()

    cfg = default_config
    if args.model:
        cfg.model_name = args.model
    if args.provider:
        cfg.llm_provider = args.provider
    if args.safe_mode:
        cfg.confirm_risky_actions = True

    target_goal = args.goal or args.task

    if args.desktop:
        import jev_desktop
        jev_desktop.main()
        return

    if target_goal and not args.interactive:
        # Ejecución directa estilo Claude Code no interactivo
        start_time = time.time()
        set_agent_status(state="thinking", task=target_goal, running=True, thought="Iniciando tarea...")
        def _dt(t):
            set_agent_status(state="thinking", thought=str(t)[:160], running=True)
            if console: display_thought(t)
            else: print(f"[Pensamiento] {t}")
        def _dc(n, a):
            set_agent_status(state="tool", tool=n, tool_args=str(a)[:140], tool_in_progress=True, running=True)
            if console: display_tool_call(n, a)
            else: print(f"[Acción] {n}: {a}")
        def _dr(n, r):
            ok = getattr(r, "success", True) if hasattr(r, "success") else True
            set_agent_status(state="tool", tool=n, last_ok=ok, tool_in_progress=False, running=True)
            if console: display_tool_result(n, r)
            else: print(f"[Resultado] {n}")

        agent = AgentCore(
            config=cfg,
            on_thought=_dt,
            on_tool_call=_dc,
            on_tool_result=_dr
        )
        try:
            res = agent.run_task(target_goal)
            elapsed = time.time() - start_time
            if console:
                display_final_answer(res, elapsed_seconds=elapsed)
            else:
                print(f"\n{res}\n")
        finally:
            set_agent_status(state="idle", thought="Completado", running=False, last_ok=True)
    else:
        run_interactive_session(cfg)


if __name__ == "__main__":
    main()
