"""
Módulo de Notificaciones y Síntesis de Voz Local (core.notifications).
Integración de Piper TTS de bajo consumo y notificador no bloqueante.
"""
from core.notifications.events import (
    NotificationEvent,
    NotificationPriority,
    EventType
)
from core.notifications.piper_tts import PiperTTS
from core.notifications.voice_notifier import VoiceNotifier

__all__ = [
    "NotificationEvent",
    "NotificationPriority",
    "EventType",
    "PiperTTS",
    "VoiceNotifier"
]
