"""
Definición de Eventos y Prioridades para el Sistema de Notificaciones del Agente (core.notifications.events).
"""
from dataclasses import dataclass, field
from enum import Enum, IntEnum
import time
from typing import Optional, Dict, Any


class NotificationPriority(IntEnum):
    """Prioridad de la notificación (menor número = mayor prioridad en cola)."""
    CRITICAL = 0    # Errores graves, parada de emergencia, violaciones de seguridad
    HIGH = 1        # Tarea completada, advertencias de guardrails
    NORMAL = 2      # Progreso de microtareas, cambios de fase
    LOW = 3         # Pensamientos internos, detalles no esenciales


class EventType(str, Enum):
    """Tipos de eventos emitidos durante el ciclo de vida del agente."""
    TASK_STARTED = "task_started"
    SUBTASK_PROGRESS = "subtask_progress"
    TOOL_EXECUTING = "tool_executing"
    TOOL_FAILED = "tool_failed"
    GUARDRAIL_TRIGGERED = "guardrail_triggered"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    SYSTEM_ALERT = "system_alert"


@dataclass(order=True)
class NotificationEvent:
    """Evento estructurado de notificación con soporte para ordenamiento por prioridad."""
    priority: int
    timestamp: float = field(compare=False)
    text: str = field(compare=False)
    event_type: str = field(compare=False, default=EventType.SUBTASK_PROGRESS.value)
    language: str = field(compare=False, default="es")
    metadata: Optional[Dict[str, Any]] = field(compare=False, default=None)

    @classmethod
    def create(
        cls,
        text: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        event_type: EventType = EventType.SUBTASK_PROGRESS,
        language: str = "es",
        metadata: Optional[Dict[str, Any]] = None
    ) -> "NotificationEvent":
        return cls(
            priority=int(priority),
            timestamp=time.time(),
            text=text.strip(),
            event_type=event_type.value if isinstance(event_type, EventType) else str(event_type),
            language=language,
            metadata=metadata or {}
        )
