"""
Gestor Unificado de Salvaguardas y Presupuesto (core.guardrails.manager).
Orquesta Circuit Breakers, Detección de Flapping y Límites de Presupuesto
para proteger el ciclo de ejecución autónoma del MMAE-Agent.
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass
import time
import logging

from core.guardrails.circuit_breaker import ToolCircuitBreaker, CircuitBreakerState
from core.guardrails.flapping_detector import ToolFlappingDetector
from core.guardrails.budget_guard import ExecutionBudgetGuard

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GuardrailDecision:
    """Decisión de salvaguarda sobre la invocación de una herramienta."""
    allowed: bool
    reason: str
    suggested_action: Optional[str] = None
    source: str = "guardrails"

    def to_feedback(self) -> str:
        """Genera mensaje de feedback estructurado para el LLM."""
        msg = f"⛔ ACCIÓN BLOQUEADA POR SALVAGUARDA ({self.source.upper()}):\n{self.reason}"
        if self.suggested_action:
            msg += f"\n👉 Acción correctiva requerida: {self.suggested_action}"
        return msg


class GuardrailManager:
    """
    Orquestador integral de salvaguardas de ejecución y presupuesto.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_cooldown_seconds: float = 30.0,
        max_task_iterations: int = 25,
        max_subtask_iterations: int = 6,
        max_task_duration_seconds: float = 300.0,
        max_total_tool_calls: int = 50
    ):
        self.circuit_breaker = ToolCircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_cooldown_seconds=recovery_cooldown_seconds
        )
        self.flapping_detector = ToolFlappingDetector()
        self.budget_guard = ExecutionBudgetGuard(
            max_task_iterations=max_task_iterations,
            max_subtask_iterations=max_subtask_iterations,
            max_task_duration_seconds=max_task_duration_seconds,
            max_total_tool_calls=max_total_tool_calls
        )

    def start_task(self) -> None:
        """Inicializa las salvaguardas para una nueva tarea."""
        self.budget_guard.start_task()
        self.flapping_detector.reset()

    def step_started(self, subtask_id: Optional[str] = None) -> None:
        """Notifica el inicio de una nueva iteración de ReAct."""
        self.budget_guard.increment_iteration(subtask_id=subtask_id)

    def verify_invocation(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        subtask_id: Optional[str] = None
    ) -> GuardrailDecision:
        """
        Verificación pre-ejecución de una herramienta.
        Inspecciona presupuesto, flapping y estado del circuit breaker.
        """
        # 1. Verificar presupuesto de ejecución
        budget_ok, budget_reason, budget_fix = self.budget_guard.check_budget(subtask_id=subtask_id)
        if not budget_ok:
            return GuardrailDecision(
                allowed=False,
                reason=budget_reason,
                suggested_action=budget_fix,
                source="budget_guard"
            )

        # 2. Verificar detección de flapping
        is_flapping, flap_reason, flap_fix = self.flapping_detector.check_flapping(tool_name)
        if is_flapping:
            return GuardrailDecision(
                allowed=False,
                reason=flap_reason,
                suggested_action=flap_fix,
                source="flapping_detector"
            )

        # 3. Verificar estado del Circuit Breaker para esta herramienta
        cb_ok, cb_reason, cb_fix = self.circuit_breaker.can_execute(tool_name, tool_args)
        if not cb_ok:
            return GuardrailDecision(
                allowed=False,
                reason=cb_reason,
                suggested_action=cb_fix,
                source="circuit_breaker"
            )

        # Invocación aprobada
        return GuardrailDecision(allowed=True, reason="OK", source="guardrails")

    def record_result(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        success: bool,
        duration_ms: float = 0.0,
        error: Optional[str] = None
    ) -> None:
        """
        Registra el resultado empírico post-ejecución de la herramienta.
        Actualiza contadores de presupuesto, historial de flapping y circuit breakers.
        """
        self.budget_guard.increment_tool_call()
        now = time.time()
        self.flapping_detector.record_call(tool_name, tool_args, success=success, timestamp=now)

        if success:
            self.circuit_breaker.record_success(tool_name, tool_args)
        else:
            reason = error or "Fallo en la ejecución de la herramienta"
            self.circuit_breaker.record_failure(tool_name, reason=reason, tool_args=tool_args)

    def reset_all(self) -> None:
        """Reinicia todos los subsistemas de salvaguarda."""
        self.circuit_breaker.reset_all()
        self.flapping_detector.reset()
        self.budget_guard.reset()
