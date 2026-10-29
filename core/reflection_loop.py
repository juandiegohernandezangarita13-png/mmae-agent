from typing import Dict, Any, Callable
from core.memory import ExecutionMemory

class ReflectionLoop:
    """
    Supervisa la ejecución de tareas. Si falla un paso, retroalimenta al agente
    hasta agotar los reintentos permitidos.
    """
    def __init__(self, memory: ExecutionMemory, max_retries: int = 3):
        self.memory = memory
        self.max_retries = max_retries

    def execute_with_retry(self, action_name: str, step_function: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        retries = 0
        last_result = {}

        while retries < self.max_retries:
            last_result = step_function()
            self.memory.record_step(action_name, last_result)

            if last_result.get("success", False):
                return last_result

            retries += 1
            print(f"⚠️ Fallo en '{action_name}'. Reintento {retries}/{self.max_retries}...")

        return {
            "success": False,
            "error": f"Acción '{action_name}' falló tras {self.max_retries} intentos. Último error: {last_result.get('error')}"
        }
