from core.macro_engine import MacroEngine
from core.micro_engine import MicroEngine
from core.memory import ExecutionMemory
from core.reflection_loop import ReflectionLoop
from skills.base import SkillRegistry
from skills.terminal import SafeTerminalSkill
from skills.filesystem import SafeFileSystemSkill

def setup_agent():
    # 1. Inicializar infraestructura y memoria
    memory = ExecutionMemory(max_history=20)
    loop = ReflectionLoop(memory=memory, max_retries=3)
    registry = SkillRegistry()

    # 2. Registrar herramientas disponibles
    terminal = SafeTerminalSkill(default_timeout=30)
    fs = SafeFileSystemSkill()

    registry.register("run_terminal", "Ejecuta un comando en terminal.")(terminal.run)
    registry.register("read_file", "Lee el contenido de un archivo.")(fs.read_file)
    registry.register("write_file", "Escribe contenido en un archivo.")(fs.write_file)

    # 3. Inicializar motores Macro y Micro
    macro = MacroEngine(api_base_url="http://localhost:8000/v1")
    micro = MicroEngine(api_base_url="http://localhost:8000/v1")

    return {
        "macro": macro,
        "micro": micro,
        "memory": memory,
        "loop": loop,
        "registry": registry
    }

def execute_autonomous_goal(goal: str):
    print(f"🎯 [Objetivo]: {goal}")
    agent = setup_agent()

    # Paso 1: Generar plan Macro teniendo en cuenta el contexto previo
    print("📋 [Fase 1] Generando esqueleto de acción...")
    skeleton_data = agent["macro"].generate_skeleton(goal)
    print(f"Plan base:\n{skeleton_data['skeleton']}\n")

    # Paso 2: Desarrollar la acción en fase Micro
    print("⚙️ [Fase 2] Generando especificación exacta de la tarea...")
    detailed_step = agent["micro"].expand_skeleton(skeleton_data)
    print(f"Paso detallado:\n{detailed_step}\n")

    print("✅ Sistema orquestado y listo para ejecución de herramientas.")
    return detailed_step

if __name__ == "__main__":
    task = "Inspeccionar el repositorio local, listar los archivos en '.' y reportar dependencias."
    execute_autonomous_goal(task)
