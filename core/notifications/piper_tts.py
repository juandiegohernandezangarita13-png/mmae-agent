"""
Motor de Síntesis de Voz Local con Piper TTS (core.notifications.piper_tts).
Sintetiza texto a voz 100% en CPU con baja latencia mediante modelos ONNX ligeros.
Soporta modelos en español (es_ES-davefx-medium) e inglés (en_US-lessac-medium),
con fallback resiliente a síntesis nativa de Windows (SAPI5/PowerShell).
"""
import os
import sys
import wave
import urllib.request
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Intentar importar la biblioteca oficial piper
try:
    import piper
    from piper import PiperVoice, PiperConfig
    PIPER_AVAILABLE = True
except Exception:
    piper = None
    PiperVoice = None
    PIPER_AVAILABLE = False


class PiperTTS:
    """
    Wrapper de síntesis de voz local para Piper TTS.
    Gestiona modelos ONNX ligeros en CPU sin requerir VRAM de la GPU.
    """

    VOICE_CATALOG = {
        "es": {
            "name": "es_ES-davefx-medium",
            "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx",
            "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json"
        },
        "en": {
            "name": "en_US-lessac-medium",
            "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
            "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
        }
    }

    def __init__(
        self,
        models_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
        auto_download: bool = False
    ):
        self.models_dir = Path(models_dir or "data/models/piper").resolve()
        self.cache_dir = Path(cache_dir or "data/cache/audio").resolve()
        self.auto_download = auto_download
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._loaded_voices: Dict[str, Any] = {}

    def get_model_paths(self, language: str = "es") -> Tuple[Path, Path]:
        """Devuelve las rutas locales esperadas para el archivo .onnx y .onnx.json."""
        lang_key = "es" if language.lower().startswith("es") else "en"
        voice_info = self.VOICE_CATALOG.get(lang_key, self.VOICE_CATALOG["es"])
        model_name = voice_info["name"]
        onnx_path = self.models_dir / f"{model_name}.onnx"
        json_path = self.models_dir / f"{model_name}.onnx.json"
        return onnx_path, json_path

    def is_model_available(self, language: str = "es") -> bool:
        """Comprueba si el modelo ONNX y su archivo de configuración existen en disco."""
        onnx_p, json_p = self.get_model_paths(language)
        return onnx_p.exists() and json_p.exists() and onnx_p.stat().st_size > 1024

    def download_model(self, language: str = "es", timeout: float = 60.0) -> bool:
        """
        Descarga el modelo ONNX ligero y su configuración desde Hugging Face.
        """
        lang_key = "es" if language.lower().startswith("es") else "en"
        voice_info = self.VOICE_CATALOG.get(lang_key, self.VOICE_CATALOG["es"])
        onnx_p, json_p = self.get_model_paths(lang_key)

        try:
            logger.info("Descargando modelo Piper ONNX para [%s]: %s", lang_key, voice_info['name'])
            # Descargar JSON de configuración
            if not json_p.exists():
                urllib.request.urlretrieve(voice_info["json_url"], str(json_p))

            # Descargar modelo ONNX
            if not onnx_p.exists():
                urllib.request.urlretrieve(voice_info["onnx_url"], str(onnx_p))

            return self.is_model_available(language)
        except Exception as e:
            logger.warning("No se pudo descargar el modelo Piper (%s): %s", voice_info['name'], e)
            return False

    def load_voice(self, language: str = "es") -> Optional[Any]:
        """Carga en memoria el modelo Piper optimizado para inferencia en CPU."""
        if not PIPER_AVAILABLE:
            return None

        lang_key = "es" if language.lower().startswith("es") else "en"
        if lang_key in self._loaded_voices:
            return self._loaded_voices[lang_key]

        onnx_p, json_p = self.get_model_paths(lang_key)
        if not self.is_model_available(lang_key):
            if self.auto_download:
                self.download_model(lang_key)
            else:
                return None

        if onnx_p.exists() and json_p.exists():
            try:
                voice = PiperVoice.load(model_path=str(onnx_p), config_path=str(json_p), use_cuda=False)
                self._loaded_voices[lang_key] = voice
                logger.info("Modelo Piper TTS cargado exitosamente en CPU: %s", onnx_p.name)
                return voice
            except Exception as e:
                logger.error("Error al instanciar PiperVoice con %s: %s", onnx_p, e)
                return None
        return None

    def synthesize(
        self,
        text: str,
        output_path: Optional[Path] = None,
        language: str = "es"
    ) -> Path:
        """
        Sintetiza texto a audio WAV.
        Utiliza Piper ONNX si el modelo está disponible; si no, aplica fallback nativo de Windows (SAPI5/PowerShell).
        """
        clean_text = text.strip()
        out_path = output_path or (self.cache_dir / f"tts_{abs(hash(clean_text)) % 1000000}.wav")

        voice = self.load_voice(language)
        if voice is not None:
            try:
                with wave.open(str(out_path), "wb") as wav_file:
                    voice.synthesize_wav(clean_text, wav_file)
                if out_path.exists() and out_path.stat().st_size > 100:
                    return out_path
            except Exception as e:
                logger.warning("Fallo al sintetizar con Piper: %s. Ejecutando fallback...", e)

        # Fallback a SAPI5 de Windows mediante PowerShell
        return self._synthesize_windows_fallback(clean_text, out_path)

    def _synthesize_windows_fallback(self, text: str, out_path: Path) -> Path:
        """
        Generador acústico o SAPI5 local para garantizar que nunca falte el archivo de audio.
        """
        escaped_text = text.replace('"', '""').replace("'", "''")
        ps_script = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{str(out_path).replace(chr(92), chr(92)+chr(92))}'); "
            f"$s.Speak('{escaped_text}'); "
            f"$s.Dispose()"
        )
        try:
            import subprocess
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False
            )
            if out_path.exists() and out_path.stat().st_size > 100:
                return out_path
        except Exception:
            pass

        # Generador de tono acústico básico de seguridad si SAPI5 no está presente
        return self._create_beep_wav(out_path)

    @staticmethod
    def _create_beep_wav(out_path: Path) -> Path:
        """Genera un tono sinusoidal WAV ligero en caso de fallo catastrófico de sintetizadores."""
        import math
        import struct
        sample_rate = 16000
        duration = 0.3
        freq = 440.0
        num_samples = int(sample_rate * duration)
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            data = bytearray()
            for i in range(num_samples):
                val = int(math.sin(2 * math.pi * freq * (i / sample_rate)) * 16000)
                data.extend(struct.pack("<h", val))
            wf.writeframes(data)
        return out_path
