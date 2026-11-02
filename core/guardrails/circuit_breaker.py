"""
Patrón Circuit Breaker para Salvaguarda de Herramientas del Agente (core.guardrails.circuit_breaker).
Previene llamadas recursivas infinitas y fallos en cascada cuando una herramienta
del sistema o API externa falla repetidamente.
"""
import time
import json
from enum import Enum
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


class CircuitBreakerState(str, Enum):
    CLOSED = "CLOSED"         # Normal: llamadas permitidas
    OPEN = "OPEN"             # Bloqueado: llamadas interceptadas y denegadas
    HALF_OPEN = "HALF_OPEN"   # Prueba: se permite una llamada de verificación


@dataclass
class ToolBreakerStatus:
    tool_name: str
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_time: float = 0.0
    last_failure_reason: str = ""
    trip_count: int = 0


class ToolCircuitBreaker:
    """
    Controlador de Circuit Breakers por herramienta individual y global.
    - Se dispara (OPEN) tras N fallos consecutivos.
    - Se recupera (HALF_OPEN -> CLOSED) tras cooldown de enfriamiento si la prueba tiene éxito.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_cooldown_seconds: float = 30.0,
        max_identical_call_threshold: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_cooldown_seconds = recovery_cooldown_seconds
        self.max_identical_call_threshold = max_identical_call_threshold

        self.breakers: Dict[str, ToolBreakerStatus] = {}
        self.call_signatures_count: Dict[str, int] = {}

    def _get_status(self, tool_name: str) -> ToolBreakerStatus:
        if tool_name not in self.breakers:
            self.breakers[tool_name] = ToolBreakerStatus(tool_name=tool_name)
        return self.breakers[tool_name]

    def _compute_signature(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        try:
            serialized = json.dumps(tool_args, sort_keys=True)
        except Exception:
            serialized = str(tool_args)
        return f"{tool_name}:{serialized}"

    def can_execute(self, tool_name: str, tool_args: Optional[Dict[str, Any]] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Verifica si la herramienta tiene permitido ejecutarse según su breaker.
        Retorna (permitido: bool, motivo: str, accion_sugerida: Optional[str]).
        """
        status = self._get_status(tool_name)
        now = time.time()

        # 1. Comprobar llamadas con argumentos idénticos repetidos
        if tool_args is not None:
            sig = self._compute_signature(tool_name, tool_args)
            sig_count = self.call_signatures_count.get(sig, 0)
            if sig_count >= self.max_identical_call_threshold:
                return (
                    False,
                    f"CIRCUIT BREAKER: La acción '{tool_name}' ha sido invocada {sig_count} veces con argumentos idénticos sin progreso.",
                    f"Tienes prohibido repetir los mismos argumentos en '{tool_name}'. Usa una herramienta distinta o cambia los parámetros."
                )

        # 2. Si el breaker está OPEN, comprobar si expiró el tiempo de enfriamiento
        if status.state == CircuitBreakerState.OPEN:
            elapsed = now - status.last_failure_time
            if elapsed >= self.recovery_cooldown_seconds:
                status.state = CircuitBreakerState.HALF_OPEN
                return (
                    True,
                    f"CIRCUIT BREAKER [HALF_OPEN]: Permitiendo llamada de prueba para '{tool_name}' tras periodo de enfriamiento ({elapsed:.1f}s).",
                    None
                )
            remaining = self.recovery_cooldown_seconds - elapsed
            return (
                False,
                f"CIRCUIT BREAKER [OPEN]: La herramienta '{tool_name}' está bloqueada por fallos reiterados ({status.consecutive_failures} fallos). Último error: '{status.last_failure_reason}'.",
                f"Espera {remaining:.1f}s para recuperación o recurre a una herramienta alternativa de inmediato."
            )

        return (True, "OK", None)

    def record_success(self, tool_name: str, tool_args: Optional[Dict[str, Any]] = None) -> None:
        """Registra un éxito para la herramienta, restableciendo el breaker."""
        status = self._get_status(tool_name)
        status.total_successes += 1
        status.consecutive_failures = 0
        status.state = CircuitBreakerState.CLOSED

        # Reset de firmas si tuvo éxito
        if tool_args is not None:
            sig = self._compute_signature(tool_name, tool_args)
            self.call_signatures_count.pop(sig, None)

    def record_failure(self, tool_name: str, reason: str, tool_args: Optional[Dict[str, Any]] = None) -> None:
        """Registra un fallo. Si excede el umbral, abre el circuit breaker."""
        status = self._get_status(tool_name)
        status.total_failures += 1
        status.consecutive_failures += 1
        status.last_failure_time = time.time()
        status.last_failure_reason = reason[:200]

        if tool_args is not None:
            sig = self._compute_signature(tool_name, tool_args)
            self.call_signatures_count[sig] = self.call_signatures_count.get(sig, 0) + 1

        if status.consecutive_failures >= self.failure_threshold:
            status.state = CircuitBreakerState.OPEN
            status.trip_count += 1

    def reset_all(self) -> None:
        """Restablece todos los circuit breakers a estado CLOSED."""
        self.breakers.clear()
        self.call_signatures_count.clear()
