"""
Servicio de Notificación por Voz No Bloqueante en Segundo Plano (core.notifications.voice_notifier).
Permite al agente emitir avisos hablados sobre el progreso, advertencias y conclusiones
de tareas en un hilo secundario sin congelar el bucle principal ReAct.
"""
import threading
import queue
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from core.notifications.events import NotificationEvent, NotificationPriority, EventType
from core.notifications.piper_tts import PiperTTS

logger = logging.getLogger(__name__)


class VoiceNotifier:
    """
    Gestor asíncrono y no bloqueante de notificaciones sonoras y por voz.
    Utiliza una cola de prioridad y un hilo daemon para procesar las síntesis
    sin impacto en la latencia del bucle cognitivo.
    """

    def __init__(
        self,
        tts_engine: Optional[PiperTTS] = None,
        enabled: bool = True,
        default_language: str = "es"
    ):
        self.tts = tts_engine or PiperTTS()
        self.enabled = enabled
        self.default_language = default_language

        self._queue: queue.PriorityQueue[NotificationEvent] = queue.PriorityQueue()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Historial de notificaciones emitidas
        self.history = []

        if self.enabled:
            self._start_worker()

    def _start_worker(self) -> None:
        """Inicia el hilo trabajador de segundo plano."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="VoiceNotifierWorker",
                daemon=True
            )
            self._worker_thread.start()

    def _worker_loop(self) -> None:
        """Bucle consumidor que procesa la síntesis y reproducción de audio en background."""
        while not self._stop_event.is_set():
            try:
                # Esperar eventos con timeout de 0.5s para revisar _stop_event
                event: NotificationEvent = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if not self.enabled:
                    self._queue.task_done()
                    continue

                # 1. Sintetizar a archivo WAV temporal usando Piper TTS
                wav_path = self.tts.synthesize(
                    text=event.text,
                    language=event.language or self.default_language
                )

                # 2. Reproducir el archivo generado de forma segura
                self._play_audio(wav_path)

                self.history.append({
                    "timestamp": event.timestamp,
                    "event_type": event.event_type,
                    "text": event.text,
                    "priority": event.priority
                })

            except Exception as e:
                logger.error("Error al procesar notificación de voz: %s", e)
            finally:
                self._queue.task_done()

    def _play_audio(self, wav_path: Path) -> None:
        """Reproduce un archivo WAV en Windows de forma nativa en el hilo del worker."""
        if not wav_path.exists():
            return

        try:
            # En Windows, winsound.PlaySound es nativo del kernel y no requiere librerías pesadas
            if sys_platform_is_win32():
                import winsound
                # SND_FILENAME sincrónico dentro del hilo worker (no bloquea el hilo principal del agente)
                winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
            else:
                import subprocess
                subprocess.run(["aplay", str(wav_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.debug("Reproducción de audio no completada: %s", e)

    def notify(
        self,
        text: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        event_type: EventType = EventType.SUBTASK_PROGRESS,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Encola un mensaje para ser sintetizado y hablado en segundo plano.
        Retorno inmediato (< 1ms), 100% no bloqueante.
        """
        if not self.enabled or not text.strip():
            return

        event = NotificationEvent.create(
            text=text,
            priority=priority,
            event_type=event_type,
            language=language or self.default_language,
            metadata=metadata
        )
        self._queue.put(event)

    # Métodos convenientes para el ciclo de vida del agente:
    def notify_task_started(self, task_goal: str) -> None:
        short_task = task_goal[:80]
        self.notify(
            text=f"Iniciando tarea: {short_task}",
            priority=NotificationPriority.NORMAL,
            event_type=EventType.TASK_STARTED
        )

    def notify_progress(self, subtask_title: str) -> None:
        self.notify(
            text=f"Avanzando: {subtask_title[:60]}",
            priority=NotificationPriority.NORMAL,
            event_type=EventType.SUBTASK_PROGRESS
        )

    def notify_error(self, error_desc: str) -> None:
        self.notify(
            text=f"Atención: {error_desc[:70]}",
            priority=NotificationPriority.HIGH,
            event_type=EventType.TOOL_FAILED
        )

    def notify_guardrail_blocked(self, reason: str) -> None:
        self.notify(
            text="Acción bloqueada por salvaguardas de seguridad.",
            priority=NotificationPriority.CRITICAL,
            event_type=EventType.GUARDRAIL_TRIGGERED
        )

    def notify_completed(self, summary: str = "Tarea finalizada con éxito.") -> None:
        self.notify(
            text=summary[:80],
            priority=NotificationPriority.HIGH,
            event_type=EventType.TASK_COMPLETED
        )

    def set_enabled(self, enabled: bool) -> None:
        """Activa o silencia las notificaciones por voz."""
        self.enabled = enabled
        if enabled:
            self._start_worker()

    def shutdown(self, timeout: float = 2.0) -> None:
        """Detiene el hilo secundario de notificaciones."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)


def sys_platform_is_win32() -> bool:
    import sys
    return sys.platform == "win32"
