"""
Módulo de Salvaguardas de Ejecución y Presupuesto para MMAE-Agent (core.guardrails).
Incluye Circuit Breakers, Detección de Flapping de Herramientas y Control de Presupuesto.
"""
from core.guardrails.circuit_breaker import (
    CircuitBreakerState,
    ToolBreakerStatus,
    ToolCircuitBreaker
)
from core.guardrails.flapping_detector import (
    ToolFlappingDetector,
    ToolCallRecord
)
from core.guardrails.budget_guard import (
    ExecutionBudgetGuard
)
from core.guardrails.manager import (
    GuardrailManager,
    GuardrailDecision
)

__all__ = [
    "CircuitBreakerState",
    "ToolBreakerStatus",
    "ToolCircuitBreaker",
    "ToolFlappingDetector",
    "ToolCallRecord",
    "ExecutionBudgetGuard",
    "GuardrailManager",
    "GuardrailDecision"
]
