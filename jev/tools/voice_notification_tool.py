"""
Herramienta de Notificación por Voz Local con Piper (jev.tools.voice_notification_tool).
Permite al agente emitir notificaciones habladas locales no bloqueantes sobre el estado o progreso.
"""
from typing import Dict, Any, Optional
from jev.tools.base import BaseTool, ToolResult
from core.notifications import VoiceNotifier, NotificationPriority, EventType


class VoiceNotificationTool(BaseTool):
    """Herramienta de síntesis de voz y notificaciones habladas no bloqueantes."""
    name = "speak_notification"
    description = (
        "Emite una notificación hablada local en segundo plano (TTS con Piper en CPU). "
        "Permite alertar al usuario sobre el progreso, advertencias o finalización de una tarea "
        "sin pausar el bucle principal."
    )
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Texto o mensaje a pronunciar en voz alta."
            },
            "priority": {
                "type": "string",
                "enum": ["normal", "high", "critical", "low"],
                "description": "Nivel de prioridad del aviso."
            },
            "language": {
                "type": "string",
                "enum": ["es", "en"],
                "description": "Idioma de la voz (es = español, en = inglés)."
            }
        },
        "required": ["message"]
    }

    def __init__(self, notifier: Optional[VoiceNotifier] = None):
        self.notifier = notifier or VoiceNotifier()

    def execute(
        self,
        message: str,
        priority: str = "normal",
        language: str = "es",
        **kwargs
    ) -> ToolResult:
        try:
            p_map = {
                "critical": NotificationPriority.CRITICAL,
                "high": NotificationPriority.HIGH,
                "normal": NotificationPriority.NORMAL,
                "low": NotificationPriority.LOW
            }
            p_val = p_map.get(priority.lower(), NotificationPriority.NORMAL)

            self.notifier.notify(
                text=message,
                priority=p_val,
                event_type=EventType.SUBTASK_PROGRESS,
                language=language
            )

            return ToolResult(
                success=True,
                output=f"✓ Notificación de voz encolada para reproducción en segundo plano: '{message[:60]}...'",
                data={"message": message, "priority": priority, "language": language}
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error al emitir voz: {str(e)}")
