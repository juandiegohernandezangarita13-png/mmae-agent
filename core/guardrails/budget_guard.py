"""
Salvaguarda de Presupuesto y Límites de Iteración (core.guardrails.budget_guard).
Previene bucles autónomos descontrolados imponiendo límites estrictos de pasos
por microtarea, iteraciones globales y tiempo máximo de ejecución.
"""
import time
from typing import Tuple, Optional, Dict


class ExecutionBudgetGuard:
    """
    Controlador de presupuestos de ejecución para tareas autónomas.
    """

    def __init__(
        self,
        max_task_iterations: int = 25,
        max_subtask_iterations: int = 6,
        max_task_duration_seconds: float = 300.0,
        max_total_tool_calls: int = 50
    ):
        self.max_task_iterations = max_task_iterations
        self.max_subtask_iterations = max_subtask_iterations
        self.max_task_duration_seconds = max_task_duration_seconds
        self.max_total_tool_calls = max_total_tool_calls

        self.task_start_time: float = 0.0
        self.global_iteration_count: int = 0
        self.total_tool_calls: int = 0
        self.subtask_iterations: Dict[str, int] = {}
        self.active_subtask_id: Optional[str] = None

    def start_task(self) -> None:
        """Inicia el cronómetro y los contadores para una nueva tarea."""
        self.task_start_time = time.time()
        self.global_iteration_count = 0
        self.total_tool_calls = 0
        self.subtask_iterations.clear()
        self.active_subtask_id = None

    def increment_iteration(self, subtask_id: Optional[str] = None) -> None:
        """Incrementa el contador global y el de la subtarea activa."""
        self.global_iteration_count += 1
        if subtask_id:
            self.active_subtask_id = str(subtask_id)
            self.subtask_iterations[self.active_subtask_id] = self.subtask_iterations.get(self.active_subtask_id, 0) + 1

    def increment_tool_call(self) -> None:
        """Incrementa el contador de llamadas a herramientas."""
        self.total_tool_calls += 1

    def check_budget(self, subtask_id: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Evalúa si la ejecución actual permanece dentro de los límites presupuestarios.
        Retorna (dentro_de_presupuesto: bool, motivo: str, accion_sugerida: Optional[str]).
        """
        # 1. Comprobar límite de tiempo de pared
        if self.task_start_time > 0:
            elapsed = time.time() - self.task_start_time
            if elapsed > self.max_task_duration_seconds:
                return (
                    False,
                    f"PRESUPUESTO AGOTADO: Tiempo límite de tarea excedido ({elapsed:.1f}s > {self.max_task_duration_seconds:.1f}s).",
                    "Finaliza inmediatamente la tarea entregando el mejor resultado disponible o reportando estado actual."
                )

        # 2. Comprobar límite de iteraciones globales de la tarea
        if self.global_iteration_count >= self.max_task_iterations:
            return (
                False,
                f"PRESUPUESTO AGOTADO: Límite de iteraciones globales alcanzado ({self.global_iteration_count}/{self.max_task_iterations}).",
                "Detén el bucle ReAct para evitar recursión infinita y formula la respuesta final de conclusión."
            )

        # 3. Comprobar límite de iteraciones por microtarea individual
        target_subtask = str(subtask_id) if subtask_id else self.active_subtask_id
        if target_subtask:
            sub_count = self.subtask_iterations.get(target_subtask, 0)
            if sub_count >= self.max_subtask_iterations:
                return (
                    False,
                    f"PRESUPUESTO AGOTADO: Microtarea [{target_subtask}] excedió su límite ({sub_count}/{self.max_subtask_iterations} pasos).",
                    f"Marca la microtarea [{target_subtask}] como bloqueada y avanza obligatoriamente a la siguiente subtarea o estrategia alternativa."
                )

        # 4. Comprobar límite de llamadas totales a herramientas
        if self.total_tool_calls >= self.max_total_tool_calls:
            return (
                False,
                f"PRESUPUESTO AGOTADO: Se superó el volumen máximo de llamadas a herramientas ({self.total_tool_calls}/{self.max_total_tool_calls}).",
                "Concluye la tarea con los datos recopilados hasta el momento."
            )

        return (True, "OK", None)

    def reset(self) -> None:
        """Reinicia todos los presupuestos."""
        self.start_task()
