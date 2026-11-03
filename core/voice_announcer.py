"""
Módulo Voice Announcer: Actuador de voz asíncrono vía Fish Audio y fallback local.
Diseñado para operar desacoplado en un hilo de fondo (non-blocking) con cola de prioridad,
garantizando que la síntesis y reproducción de audio no congele la animación Canvas 2D
ni la interfaz del widget flotante de escritorio en `jev_desktop.py`.

Variables de entorno soportadas:
- `FISH_API_KEY`: Clave de autenticación para la API REST de Fish Audio (https://fish.audio).
- `FISH_VOICE_ID`: Identificador de referencia de la voz clonada/modelo (opcional).
- `FISH_API_URL`: Endpoint de síntesis (por defecto https://api.fish.audio/v1/tts).
- `VOICE_ENABLED`: Activar/desactivar reproducción sonora ("1" o "true").
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from config import BASE_DIR
from utils.logger import log

# Intentar sincronizar con el estado de la Isla MMAE si está disponible
try:
    from jev.core.status_sync import set_agent_status
except Exception:
    def set_agent_status(**kwargs: Any) -> None:  # type: ignore
        pass


@dataclass
class VoiceNotice:
    """Mensaje estructurado para la cola de voz."""
    text: str
    priority: str = "normal"  # "high", "normal", "hitl"
    created_at: float = 0.0


class FishAudioClient:
    """Cliente HTTP asíncrono y resiliente para la API de Fish Audio."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("FISH_API_KEY", "")
        self.voice_id = voice_id or os.getenv("FISH_VOICE_ID", "")
        self.api_url = api_url or os.getenv("FISH_API_URL", "https://api.fish.audio/v1/tts")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("tu_clave"))

    def synthesize(self, text: str, output_path: Path) -> bool:
        """Sintetiza texto a archivo de audio MP3/WAV usando la API de Fish Audio."""
        if not self.is_configured:
            return False

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "text": text,
            "format": "mp3",
        }
        if self.voice_id:
            payload["reference_id"] = self.voice_id

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=12,
            )
            if response.status_code == 200 and len(response.content) > 100:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                return True
            else:
                log.warning(f"Fish Audio devolvió status {response.status_code}: {response.text[:200]}")
        except Exception as e:
            log.warning(f"Error comunicando con Fish Audio: {e}")

        return False


class VoiceAnnouncer:
    """
    Actuador de voz desacoplado en segundo plano.
    Garantiza latencia cero para el hilo de UI/Canvas al procesar el audio mediante
    una cola asíncrona de mensajes (thread-safe).
    """

    _instance: Optional[VoiceAnnouncer] = None
    _lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> VoiceAnnouncer:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(VoiceAnnouncer, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        if getattr(self, "_initialized", False):
            return

        self.client = FishAudioClient(api_key=api_key, voice_id=voice_id)
        
        # Audio cache
        self.cache_dir = BASE_DIR / "data" / "audio_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        env_enabled = os.getenv("VOICE_ENABLED", "1").lower() in ("1", "true", "yes")
        self.enabled = env_enabled if enabled is None else enabled

        self._queue: queue.PriorityQueue[Tuple[int, VoiceNotice]] = queue.PriorityQueue()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True, name="VoiceAnnouncerWorker")
        self._worker_thread.start()

        self._initialized = True
        log.info(f"🎙️ [VoiceAnnouncer]: Inicializado (Fish Audio configurado={self.client.is_configured}, Habilitado={self.enabled}).")

    def announce(self, text: str, priority: str = "normal") -> None:
        """
        Encola un anuncio de voz de forma inmediata y no bloqueante (<1ms).
        Prioridades:
        - "hitl": 0 (Máxima prioridad, intervención humana requerida)
        - "high": 1 (Descubrimientos importantes o errores críticos)
        - "normal": 2 (Avisos generales y bucle de curiosidad)
        """
        if not self.enabled or not text.strip():
            return

        p_val = 0 if priority == "hitl" else (1 if priority == "high" else 2)
        notice = VoiceNotice(text=text.strip(), priority=priority, created_at=time.time())
        self._queue.put((p_val, notice))

    async def announce_async(self, text: str, priority: str = "normal") -> None:
        """Interfaz asíncrona no bloqueante compatible con bucles de asyncio."""
        self.announce(text, priority=priority)

    def _process_queue(self) -> None:
        """Bucle consumidor en hilo secundario para no bloquear Canvas ni el renderizado."""
        while not self._stop_event.is_set():
            try:
                p_val, notice = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._speak_notice(notice)
            except Exception as e:
                log.warning(f"Error reproduciendo aviso de voz: {e}")
            finally:
                self._queue.task_done()

    def _speak_notice(self, notice: VoiceNotice) -> None:
        """Sintetiza y reproduce el aviso sin congelar el sistema."""
        text = notice.text
        log.info(f"🔊 [Voz]: ({notice.priority}) {text}")

        # Notificar a la Isla que hay audio activo
        try:
            set_agent_status(thought=f"Voz: {text[:60]}...", state="talking")
        except Exception:
            pass

        # Generar nombre de archivo temporal en cache
        temp_audio = self.cache_dir / f"tts_{int(time.time() * 1000)}.mp3"

        played_successfully = False
        # 1. Intentar Fish Audio cloud si está configurado
        if self.client.is_configured:
            synthesized = self.client.synthesize(text, temp_audio)
            if synthesized and temp_audio.exists():
                played_successfully = self._play_audio_file(temp_audio)

        # 2. Fallback de alta velocidad: Windows Native SAPI Speech si Fish Audio no está configurado o falló
        if not played_successfully:
            self._fallback_windows_speech(text)

        # Restaurar estado en la Isla
        try:
            set_agent_status(state="idle")
        except Exception:
            pass

    def _play_audio_file(self, audio_path: Path) -> bool:
        """Reproduce un archivo de audio en Windows de forma desacoplada."""
        if sys.platform != "win32":
            return False

        try:
            # Usar mciSendString de winmm.dll para reproducción nativa y sin dependencias de GUI
            winmm = ctypes.windll.winmm
            alias = f"audio_{int(time.time() * 1000)}"
            open_cmd = f'open "{str(audio_path.resolve())}" type mpegvideo alias {alias}'
            play_cmd = f"play {alias} wait"
            close_cmd = f"close {alias}"

            res_open = winmm.mciSendStringW(open_cmd, None, 0, None)
            if res_open == 0:
                winmm.mciSendStringW(play_cmd, None, 0, None)
                winmm.mciSendStringW(close_cmd, None, 0, None)
                # Limpiar archivo temporal
                try:
                    audio_path.unlink()
                except Exception:
                    pass
                return True
        except Exception as e:
            log.warning(f"Error reproduciendo con mciSendString: {e}")

        # Fallback vía PowerShell MediaPlayer
        try:
            ps_script = f"""
            Add-Type -AssemblyName PresentationCore
            `$mediaPlayer = New-Object System.Windows.Media.MediaPlayer
            `$mediaPlayer.Open('{audio_path.resolve()}')
            `$mediaPlayer.Play()
            Start-Sleep -Seconds 3
            `$mediaPlayer.Close()
            """
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], timeout=6, capture_output=True)
            try:
                audio_path.unlink()
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _fallback_windows_speech(self, text: str) -> None:
        """Fallback offline mediante el sintetizador de voz integrado de Windows (SAPI.SpVoice)."""
        if sys.platform != "win32":
            return

        try:
            # Intentar COM SpVoice
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            # Flag 1 = SVSFlagsAsync (reproducción asíncrona sin bloquear)
            speaker.Speak(text, 1)
            return
        except Exception:
            pass

        # Fallback vía comando ligero PowerShell System.Speech
        try:
            sanitized = text.replace('"', '`"').replace("'", "''")
            ps_cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).SpeakAsync('{sanitized}')"
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            log.debug(f"Fallback SAPI falló: {e}")

    def stop(self) -> None:
        """Detiene el hilo worker limpiamente."""
        self._stop_event.set()


__all__ = ["VoiceAnnouncer", "FishAudioClient", "VoiceNotice"]
