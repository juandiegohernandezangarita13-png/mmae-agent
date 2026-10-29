"""
Punto de entrada principal para MMAE (Macro-Micro Agent Engine) y JEV.
Permite ejecutar el motor autónomo Macro-Micro vía CLI o iniciar la consola interactiva.
"""
import sys
import argparse
from typing import Optional

# Asegurar codificación UTF-8 en Windows para caracteres especiales y emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import config, default_config, AgentConfig
from core.agent import MMAEAutonomousAgent, AgentCore
from core.evaluator import OutputEvaluator
try:
    from jev.self_improvement.evaluator import SelfImprovementEvaluator
    from jev.ui.console import (
        console,
        print_banner,
        display_thought,
        display_tool_call,
        display_tool_result,
        display_final_answer,
        display_tools_table
    )
except Exception:
    console = None


def run_interactive_session(agent_config: AgentConfig) -> None:
    """Inicia una sesión de terminal interactiva con el agente autónomo."""
    if console and print_banner:
        print_banner(model_name=agent_config.model_name, workspace_path=str(agent_config.workspace_dir))
        console.print("\n[dim]Escribe tu objetivo para MMAE. Comandos especiales: '/tools', '/lessons', '/skills', '/exit'[/dim]\n")
    else:
        print(f"=== MMAE Autonomous Agent ({agent_config.model_name}) ===")
        print("Escribe tu objetivo o '/exit' para terminar.\n")

    agent = AgentCore(
        config=agent_config,
        on_thought=display_thought if console else (lambda t: print(f"[Pensamiento] {t}")),
        on_tool_call=display_tool_call if console else (lambda n, a: print(f"[Acción] {n}: {a}")),
        on_tool_result=display_tool_result if console else (lambda n, r: print(f"[Resultado] {n}"))
    ) if AgentCore else None

    evaluator = SelfImprovementEvaluator(agent.memory, agent.llm) if (agent and 'SelfImprovementEvaluator' in globals()) else None

    while True:
        try:
            prompt_str = "Tú > "
            user_input = console.input(f"[bold green]{prompt_str}[/bold green]").strip() if console else input(prompt_str).strip()
            if not user_input:
                continue

            if user_input.lower() in ["/exit", "exit", "quit", "salir"]:
                print("\nHasta pronto. Sesión finalizada.\n")
                break

            if user_input.lower() == "/tools" and agent and console:
                display_tools_table(agent.registry.list_tools())
                continue

            if user_input.lower() == "/lessons" and agent and console:
                lessons = agent.memory.get_all_lessons() if hasattr(agent.memory, "get_all_lessons") else []
                if not lessons:
                    console.print("[dim]Aún no hay lecciones aprendidas registradas.[/dim]")
                else:
                    console.print("\n[bold cyan]📚 Lecciones Aprendidas (Auto-Mejora):[/bold cyan]")
                    for item in lessons:
                        console.print(f" • [[bold yellow]{item.get('category')}[/bold yellow]]: {item.get('rule')}")
                continue

            # Ejecutar con el agente autónomo (pipeline Macro-Micro)
            if agent:
                if console:
                    console.print(f"\n[bold blue]🚀 Iniciando ejecución para:[/bold blue] {user_input}\n")
                result = agent.run_task(user_goal=user_input)
                if console:
                    display_final_answer(result)
                else:
                    print(f"\n[Respuesta]:\n{result}\n")
            else:
                mmae = MMAEAutonomousAgent(agent_config)
                mmae.run(user_input)

        except KeyboardInterrupt:
            print("\n\nOperación interrumpida por el usuario.")
            break
        except Exception as e:
            print(f"\nError: {e}")


def main():
    parser = argparse.ArgumentParser(description="MMAE - Macro-Micro Autonomous Agent Engine")
    parser.add_argument("goal", nargs="?", default=None, help="Objetivo para ejecutar en modo autónomo")
    parser.add_argument("--task", type=str, default=None, help="Objetivo o tarea específica")
    parser.add_argument("--model", type=str, default=None, help="Nombre del modelo LLM")
    parser.add_argument("--provider", type=str, default=None, help="Proveedor LLM (ollama, lmstudio, gemini)")
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
        # Ejecución del pipeline Macro-Micro autónomo
        agent = MMAEAutonomousAgent(cfg)
        agent.run(target_goal)
    else:
        run_interactive_session(cfg)


if __name__ == "__main__":
    main()
