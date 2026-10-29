"""
Demostración de Auto-Mejora y Autoprogramación con la API de Gemini para JEV.

Flujo del script:
1. Inicializa el registro de herramientas por defecto de JEV.
2. Despliega el inventario del sistema antes de consultar a Gemini.
3. Consulta a la API de Gemini (con fallback resiliente) para auditar qué herramienta falta.
4. Gemini diagnostica la carencia y genera el código completo en Python.
5. JEV sintetiza el código, valida sintaxis AST, ejecuta prueba efímera en proceso aislado.
6. JEV realiza HOT-RELOADING en memoria de ejecución (cero reinicios de proceso).
7. Ejecuta la nueva herramienta en vivo y verifica que el agente ahora posee la nueva habilidad.
"""
import sys
import os
from pathlib import Path

# Configurar encoding UTF-8 seguro para consolas de Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Agregar raíz del proyecto al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from jev.tools import build_default_registry
from jev.config import default_config
from jev.core.auto_improver import GeminiSelfImprover


def print_banner(text: str):
    print("\n" + "=" * 65)
    print(f" {text}")
    print("=" * 65)


def run_demo():
    print_banner("JEV: DEMO DE AUTOPROGRAMACIÓN ASISTIDA POR GEMINI")

    print("[1/5] Inicializando arquitectura y herramientas base de JEV...")
    registry, _ = build_default_registry()
    initial_count = len(registry.list_tools())
    print(f" -> Herramientas inicialmente registradas: {initial_count}")

    print("\n[2/5] Inicializando motor de Auto-Mejora (GeminiSelfImprover)...")
    improver = GeminiSelfImprover(
        registry=registry,
        config=default_config,
        on_log=lambda msg: print(f"    {msg}")
    )

    inventory = improver.build_system_inventory()
    print(f" -> Total subsistemas nucleares: {len(inventory['core_subsystems'])}")
    print(f" -> Herramientas persistentes en ./generated_tools/: {inventory['existing_generated_tools']}")

    print("\n[3/5] Consultando a Gemini para auditar el código y capacidades...")
    print(" -> Gemini está analizando qué capacidad de sistema en Windows falta...")
    proposal = improver.consult_gemini(focus_area="system_management")

    print("\n--- DIAGNÓSTICO RETORNADO POR GEMINI ---")
    print(f"• Diagnóstico: {proposal.get('diagnosis')}")
    print(f"• Capacidad Recomendada: {proposal.get('recommended_capability')}")
    print(f"• Nombre Técnico: {proposal.get('tool_name')}")
    print(f"• Clase Python: {proposal.get('class_name')}")
    print(f"• Descripción: {proposal.get('description')}")
    print(f"• Dependencias Requeridas: {proposal.get('required_dependencies', [])}")

    print("\n[4/5] Sintetizando código, validando sintaxis y ejecutando Hot-Reloading...")
    result = improver.synthesize_and_hot_reload(proposal)

    if not result.get("success"):
        print(f"\n❌ Error durante el proceso: {result.get('error')}")
        return

    new_tool_name = result["tool_name"]
    print(f"\n✓ Código persistido en: {result['file_path']}")
    print(f"✓ Herramienta inyectada en caliente en ToolRegistry!")

    final_count = len(registry.list_tools())
    print(f" -> Herramientas ahora en memoria: {final_count} (+{final_count - initial_count})")

    print(f"\n[5/5] Probando la nueva herramienta '{new_tool_name}' directamente desde el agente...")
    new_tool_instance = registry.get(new_tool_name)
    if new_tool_instance:
        test_run = improver._execute_smoke_test(new_tool_instance)
        print("--- RESULTADO DE LA EJECUCIÓN AUTÓNOMA ---")
        print(f"Éxito: {test_run.success}")
        print(f"Salida: {str(test_run.output)[:400]}")
        if test_run.data:
            print(f"Datos estructurados: {list(test_run.data.keys())}")
    else:
        print("⚠️ La herramienta no se encontró en el registro tras la inyección.")

    print_banner("RESULTADO FINAL: JEV SE AUTOPROGRAMÓ EXITOSAMENTE")
    print(f"JEV ahora cuenta con la herramienta '{new_tool_name}' disponible para cualquier tarea.")


if __name__ == "__main__":
    run_demo()
