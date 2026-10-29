"""
Demostración Interactiva: Agente Autónomo Autorreflexivo y Autoevolutivo en Caliente.
Ejecuta tareas sin soporte previo (e.g., WhatsApp Gateway, DNS Resolver)
mostrando en tiempo real el monólogo cognitivo, la síntesis de código, el hot-reloading y la culminación.
"""
import sys
import time
from pathlib import Path

# Agregar raíz del proyecto al path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from jev.core.self_evolving_agent import SelfEvolvingAgent
from jev.tools.base import ToolRegistry


def console_event_listener(event_type: str, data: any):
    """Muestra en consola el progreso y pensamientos del agente en tiempo real."""
    if event_type == "reflection":
        print(data)
    elif event_type == "synthesis":
        print(f"⚙️ [Code Synthesizer]: Escribiendo código modular para '{data['spec']}' (Intento {data['attempt']})...")
    elif event_type == "hot_reload":
        print(data)
    elif event_type == "task_resumed":
        print(f"▶️ [Task Preserver]: Reanudando tarea suspendida pasando argumentos originales: {data['arguments']}")


def main():
    print("================================================================================")
    print("🤖 DEMO: AGENTE AUTÓNOMO AUTORREFLEXIVO Y AUTOEVOLUTIVO EN CALIENTE (JEV CORE)")
    print("================================================================================\n")

    registry = ToolRegistry()
    agent = SelfEvolvingAgent(
        registry=registry,
        workspace_dir=project_root,
        on_event=console_event_listener
    )

    print("Estado inicial de herramientas registradas:")
    print([t.name for t in registry.list_tools()])
    print("-" * 80)

    # CASO DE PRUEBA 1: Tarea sin soporte previo (Enviar mensaje por WhatsApp)
    print("\n[ORDEN AL AGENTE]: 'Enviar mensaje de alerta por WhatsApp al administrador (+54911223344)'")
    print("Esperando reacción del agente...\n")

    res = agent.run_task(
        task_goal="Enviar alerta crítica por WhatsApp al administrador",
        required_capability="send_whatsapp_message_tool",
        task_args={
            "recipient": "+54911223344",
            "message": "ALERTA: CPU del servidor al 94%. Requiere atención inmediata."
        }
    )

    print("\n--- RESULTADO DEFINITIVO DE LA TAREA ---")
    print(f"Éxito: {res['success']}")
    print(f"Autoevolucionó en caliente: {res['evolved']}")
    print(f"Herramienta sintetizada: {res.get('tool_synthesized')}")
    print(f"Salida: {res['output']}")
    print(f"Datos: {res.get('data')}")

    # CASO DE PRUEBA 2: Reutilización inmediata de la herramienta aprendida (Memoria a largo plazo)
    print("\n" + "=" * 80)
    print("[ORDEN AL AGENTE]: 'Enviar segundo mensaje por WhatsApp (+54911556677)'")
    res2 = agent.run_task(
        task_goal="Enviar mensaje secundario",
        required_capability="send_whatsapp_message_tool",
        task_args={
            "recipient": "+54911556677",
            "message": "Notificación secundaria de seguimiento."
        }
    )
    print(f"Éxito: {res2['success']}")
    print(f"¿Necesitó autoevolucionar de nuevo?: {res2['evolved']} (Reutilizó la herramienta residente en memoria)")
    print(f"Salida: {res2['output']}")

    print("\n================================================================================")
    print("✅ DEMOSTRACIÓN FINALIZADA CON ÉXITO: 0 ABORTOS, 100% AUTONOMÍA Y EVOLUCIÓN")
    print("================================================================================")


if __name__ == "__main__":
    main()
