"""
Script Demostrativo Funcional Mínimo: Muse Spark Agent Loop en JEV.
Demuestra de forma end-to-end:
1. El Canal de Intención Previa (Commentary/Thought Channel) antes de cada acción.
2. Planificación estructurada en pasos persistidos en SQLite.
3. Invocación de herramientas desacopladas (subprocesos de shell y funciones Python nativas).
4. Auto-recuperación ante fallos: formulación de hipótesis y reintento con parámetros ajustados.
5. Finalización exitosa y auditoría del estado.
"""
import sys
import os
import json
import time
from pathlib import Path

# Asegurar codificación UTF-8 en consola de Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Asegurar importación de módulos de JEV
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from jev.core.muse import (
    AgentLoop,
    ToolRegistry,
    ExecutionEngine,
    ExecutionResult,
    MuseStateManager,
    PlanStep,
    StepStatus,
    LoopResult
)
from jev.core.llm_client import LocalLLMClient, LLMResponse


def setup_demo_tools(registry: ToolRegistry, workspace_dir: Path) -> None:
    """Registra herramientas de shell y funciones Python nativas para la demostración."""
    
    # 1. Herramienta de Subproceso de Consola
    registry.register_shell_command(
        name="run_shell",
        description="Ejecuta comandos de PowerShell o Bash de forma segura."
    )

    # 2. Funciones Python Nativas con validación de tipos
    def write_dataset_file(filename: str, records: list) -> dict:
        """Crea un archivo JSON con registros de datos para el pipeline."""
        target_path = workspace_dir / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        return {"status": "created", "path": str(target_path), "records_count": len(records)}

    def analyze_dataset(filename: str) -> dict:
        """Analiza un conjunto de datos y calcula métricas."""
        target_path = workspace_dir / filename
        if not target_path.exists():
            raise FileNotFoundError(f"El archivo '{filename}' no existe en {workspace_dir}. Se requiere crearlo primero.")
        
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        values = [item.get("val", 0) for item in data]
        total = sum(values)
        avg = total / len(values) if values else 0.0
        return {"total_records": len(values), "sum": total, "average": avg}

    registry.register_function("write_dataset_file", write_dataset_file, "Escribe un archivo de datos JSON en workspace.")
    registry.register_function("analyze_dataset", analyze_dataset, "Analiza un dataset existente y calcula estadísticas.")


class DemoMockLLMClient:
    """
    Cliente simulado determinista para reproducir fielmente el ciclo cognitivo
    de Muse Spark (incluyendo pensamiento, intención, fallo simulado, hipótesis y solución).
    Permite probar la arquitectura sin requerir conexión a internet ni consumo de tokens.
    """
    def __init__(self):
        self.turn = 0

    def chat(self, messages, **kwargs):
        self.turn += 1
        
        # Turno 1: Intento de análisis antes de crear el archivo (Fallo provocado intencionalmente)
        if self.turn == 1:
            payload = {
                "thought": "Inicio el Paso 1. Intentaré analizar el dataset 'metricas_demo.json' para ver si ya existe.",
                "intent": "Voy a verificar si el dataset 'metricas_demo.json' ya existe en workspace intentando analizarlo.",
                "action": "analyze_dataset",
                "params": {"filename": "metricas_demo.json"}
            }
        # Turno 2: Diagnóstico del error, formulación de HIPÓTESIS y corrección
        elif self.turn == 2:
            payload = {
                "thought": "HIPÓTESIS DE CORRECCIÓN: La función 'analyze_dataset' falló con FileNotFoundError porque el archivo aún no ha sido generado. La solución es crearlo primero usando 'write_dataset_file' con datos iniciales.",
                "intent": "Voy a generar el archivo 'metricas_demo.json' con 5 registros numéricos válidos para resolver la carencia.",
                "action": "write_dataset_file",
                "params": {
                    "filename": "metricas_demo.json",
                    "records": [{"id": 1, "val": 10}, {"id": 2, "val": 20}, {"id": 3, "val": 30}, {"id": 4, "val": 40}, {"id": 5, "val": 50}]
                }
            }
        # Turno 3: Reintento del análisis con el dataset ya existente
        elif self.turn == 3:
            payload = {
                "thought": "El dataset fue creado exitosamente. Ahora que la precondición se cumple, ejecuto 'analyze_dataset'.",
                "intent": "Voy a analizar el dataset 'metricas_demo.json' ahora que el archivo ha sido creado correctamente.",
                "action": "analyze_dataset",
                "params": {"filename": "metricas_demo.json"}
            }
        # Turno 4: Completar el Paso 1
        elif self.turn == 4:
            payload = {
                "thought": "El análisis se completó exitosamente con suma=150 y promedio=30.0. Los criterios del Paso 1 están satisfechos.",
                "intent": "Doy por completado el Paso 1 de preparación y análisis inicial.",
                "action": "complete_step",
                "params": {"summary": "Dataset creado y métricas analizadas con éxito (promedio: 30.0)."}
            }
        # Turno 5: Paso 2 - Ejecución de comando de consola (PowerShell)
        elif self.turn == 5:
            payload = {
                "thought": "Entrando al Paso 2: Verificación de Integridad. Utilizaré la consola para listar el archivo generado.",
                "intent": "Voy a ejecutar un comando de shell para inspeccionar los metadatos del archivo en disco.",
                "action": "run_shell",
                "params": {"command": "Get-ChildItem metricas_demo.json | Select-Object Name, Length, LastWriteTime"}
            }
        # Turno 6: Completar Paso 2 y Finalizar Tarea Global
        else:
            payload = {
                "thought": "El archivo fue verificado físicamente en disco. Todos los objetivos del plan han sido cumplidos.",
                "intent": "Finalizo la tarea global reportando el resumen de ejecución al usuario.",
                "action": "finish",
                "params": {"final_result": "Pipeline de análisis y verificación completado exitosamente con persistencia SQLite."}
            }

        return LLMResponse(content=json.dumps(payload, indent=2))


def run_demo(use_real_llm: bool = False):
    print("=" * 75)
    print("🤖 DEMOSTRACIÓN DE ARQUITECTURA MUSE SPARK - AGENT LOOP EN JEV")
    print("=" * 75)

    workspace = BASE_DIR / "workspace" / "muse_demo"
    workspace.mkdir(parents=True, exist_ok=True)
    demo_file = workspace / "metricas_demo.json"
    if demo_file.exists():
        demo_file.unlink()
    db_path = BASE_DIR / "data" / "memory" / "demo_muse_state.db"

    # 1. Crear registro y motor de ejecución
    registry = ToolRegistry()
    setup_demo_tools(registry, workspace)
    engine = ExecutionEngine(registry=registry, workspace_dir=workspace)
    state_mgr = MuseStateManager(db_path=db_path)

    # 2. Cliente LLM (Simulado para demo instantánea o Real si se especifica)
    llm = LocalLLMClient() if use_real_llm else DemoMockLLMClient()

    # 3. Callbacks para visualizar el Canal de Intención en vivo
    def on_thought(thought: str):
        print(f"\n🧠 [Canal de Pensamiento / Thought]:\n   {thought}")

    def on_intent(intent: str):
        print(f"💬 [Canal de Intención / Intent]:\n   \"{intent}\"")

    def on_action(action: str, params: dict):
        print(f"⚡ [Acción Estructurada]: {action}({json.dumps(params)})")

    def on_result(res: ExecutionResult):
        status = "✅ ÉXITO" if res.success else f"❌ FALLO (Exit code: {res.exit_code})"
        print(f"📊 [Resultado]: {status} - Salida: {res.output[:80] or res.error}")

    # 4. Instanciar y ejecutar el AgentLoop
    loop = AgentLoop(
        registry=registry,
        engine=engine,
        state_manager=state_mgr,
        llm_client=llm,
        max_iterations=15,
        max_retries_per_step=3,
        on_thought=on_thought,
        on_intent=on_intent,
        on_action=on_action,
        on_result=on_result
    )

    goal = "Generar un dataset numérico en workspace, analizar sus métricas y verificar su integridad mediante terminal."
    
    preplanned = [
        {"title": "Generación y Análisis de Datos", "description": "Crear y analizar métricas del dataset."},
        {"title": "Verificación Física de Integridad", "description": "Comprobar existencia y atributos en disco con shell."}
    ]

    print(f"\n🎯 META INICIAL: {goal}")
    print(f"📋 PASOS DEL PLAN: {len(preplanned)} pasos declarados.")
    print("-" * 75)

    result: LoopResult = loop.run(user_goal=goal, preplanned_steps=preplanned)

    print("\n" + "=" * 75)
    print("🏁 RESUMEN FINAL DEL BUCLE MUSE SPARK")
    print("=" * 75)
    print(f"ID de Tarea Persistida: {result.task_id}")
    print(f"Estado de Éxito Global: {result.success}")
    print(f"Pasos Completados: {result.steps_completed}/{result.total_steps}")
    print(f"Turnos Totales Ejecutados: {result.total_turns}")
    print(f"Duración: {result.duration:.2f}s")
    print(f"Salida Final: {result.final_output}")
    print(f"Base de Datos SQLite: {db_path}")
    print("=" * 75)

    state_mgr.close()
    return result


if __name__ == "__main__":
    use_live = "--live" in sys.argv
    run_demo(use_real_llm=use_live)
