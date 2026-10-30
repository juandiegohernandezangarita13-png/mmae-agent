"""
Gestor de memoria de corto plazo y reflexión para evitar bucles infinitos y redundancias.
Registra el historial de ejecuciones dentro de la sesión activa de MMAE.
"""
from typing import List, Dict, Any, Optional


class ExecutionMemory:
    """
    Gestor de memoria de corto plazo y reflexión para evitar bucles infinitos y redundancias.
    """
    def __init__(self, max_history: int = 15):
        self.max_history = max_history
        self.history: List[Dict[str, Any]] = []

    def record_step(self, macro_action: str, result: Dict[str, Any]) -> None:
        entry = {
            "action": macro_action,
            "success": result.get("success", True),
            "output": result.get("stdout") or result.get("error") or ""
        }
        self.history.append(entry)
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def get_context_summary(self) -> str:
        if not self.history:
            return "Sin acciones previas registradas."
        
        summary = ["Historial de ejecuciones previas:"]
        for idx, item in enumerate(self.history):
            status = "ÉXITO" if item["success"] else "FALLO"
            summary.append(f"{idx+1}. [{status}] {item['action']} -> {item['output'][:120]}")
        return "\n".join(summary)

    def clear(self) -> None:
        self.history.clear()
