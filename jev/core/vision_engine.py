"""
Motor de Visión y Reconocimiento Multimodal para JEV.
Permite analizar imágenes adjuntas o pegadas desde el portapapeles, transcribir texto/código,
describir diagramas, interfaces de usuario y objetos utilizando modelos locales (Ollama moondream/llava)
y APIs multimodales con fallback resiliente.
"""
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from pathlib import Path
import urllib.request
import urllib.error
import urllib.parse
import json
import base64
import time
import io
import os

from jev.config import BASE_DIR, default_config


@dataclass
class VisionAnalysisResult:
    is_success: bool
    description: str
    ocr_text: str = ""
    engine_used: str = "unknown"
    image_path: Optional[str] = None
    width: int = 0
    height: int = 0
    format: str = ""
    error: Optional[str] = None


class VisionEngine:
    """Motor de análisis visual multi-nivel con tolerancia a fallos."""

    def __init__(self, uploads_dir: Optional[Path] = None, ollama_base_url: str = "http://localhost:11434"):
        self.uploads_dir = uploads_dir or (Path(BASE_DIR) / "data" / "user_uploads")
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.ollama_base_url = ollama_base_url.rstrip("/")

    def save_image_from_base64(self, base64_str: str, prefix: str = "paste") -> Tuple[Path, str]:
        """
        Decodifica y guarda una imagen base64 (Data URI o cadena pura) en el disco.
        Retorna (Path del archivo, base64 puro sin encabezado).
        """
        raw_b64 = base64_str
        mime_type = "image/png"
        ext = ".png"

        if "," in base64_str and ";base64" in base64_str:
            header, raw_b64 = base64_str.split(",", 1)
            if "image/jpeg" in header or "image/jpg" in header:
                mime_type = "image/jpeg"
                ext = ".jpg"
            elif "image/webp" in header:
                mime_type = "image/webp"
                ext = ".webp"
            elif "image/gif" in header:
                mime_type = "image/gif"
                ext = ".gif"

        img_bytes = base64.b64decode(raw_b64)
        timestamp = int(time.time() * 1000)
        file_path = self.uploads_dir / f"{prefix}_{timestamp}{ext}"
        file_path.write_bytes(img_bytes)

        return file_path, raw_b64

    def analyze(
        self,
        image_source: str,
        user_prompt: Optional[str] = None
    ) -> VisionAnalysisResult:
        """
        Analiza una imagen a partir de una ruta de archivo local o de un string base64.
        Ejecuta el pipeline:
        1. Inspección PIL (dimensiones, formato, paleta)
        2. Inferencia Neural Local (Ollama moondream / llava)
        3. Inferencia Cloud (Gemini / OpenRouter / FCC)
        4. Fallback Estructural Local
        """
        instruction = (
            user_prompt.strip() if user_prompt and user_prompt.strip()
            else "Describe y analiza detalladamente lo que ves en esta imagen. Si hay texto, código, diagramas o interfaces de usuario, transcríbelos y explícalos con precisión."
        )

        # 1. Obtener bytes y ruta
        image_path: Optional[Path] = None
        raw_b64: str = ""
        img_bytes: bytes = b""

        if image_source.startswith("data:image") or len(image_source) > 500 and not os.path.exists(image_source):
            image_path, raw_b64 = self.save_image_from_base64(image_source)
            img_bytes = image_path.read_bytes()
        else:
            image_path = Path(image_source)
            if not image_path.exists():
                return VisionAnalysisResult(
                    is_success=False,
                    description="",
                    error=f"No se encontró el archivo de imagen en '{image_source}'."
                )
            img_bytes = image_path.read_bytes()
            raw_b64 = base64.b64encode(img_bytes).decode("ascii")

        # 2. Metadatos PIL
        width, height, img_format = 0, 0, "UNKNOWN"
        try:
            from PIL import Image
            with Image.open(io.BytesIO(img_bytes)) as pil_img:
                width, height = pil_img.size
                img_format = pil_img.format or "PNG"
        except Exception as e:
            pass

        # 3. Nivel 1: Ollama Local (moondream / llava / qwen2-vl)
        local_res = self._try_ollama_vision(raw_b64, instruction)
        if local_res and local_res.strip():
            return VisionAnalysisResult(
                is_success=True,
                description=local_res.strip(),
                engine_used="Ollama Local Vision (moondream)",
                image_path=str(image_path),
                width=width,
                height=height,
                format=img_format
            )

        # 4. Nivel 2: Free Claude Code Proxy en puerto 8082
        fcc_res = self._try_fcc_proxy_vision(raw_b64, instruction, img_format)
        if fcc_res and fcc_res.strip():
            return VisionAnalysisResult(
                is_success=True,
                description=fcc_res.strip(),
                engine_used="Free Claude Code Proxy Vision",
                image_path=str(image_path),
                width=width,
                height=height,
                format=img_format
            )

        # 5. Nivel 3: Gemini Vision API (si key disponible)
        gemini_res = self._try_gemini_vision(raw_b64, instruction, img_format)
        if gemini_res and gemini_res.strip():
            return VisionAnalysisResult(
                is_success=True,
                description=gemini_res.strip(),
                engine_used="Google Gemini Multimodal Vision",
                image_path=str(image_path),
                width=width,
                height=height,
                format=img_format
            )

        # 6. Nivel 4: OpenRouter Multimodal (si key disponible)
        or_res = self._try_openrouter_vision(raw_b64, instruction, img_format)
        if or_res and or_res.strip():
            return VisionAnalysisResult(
                is_success=True,
                description=or_res.strip(),
                engine_used="OpenRouter Vision",
                image_path=str(image_path),
                width=width,
                height=height,
                format=img_format
            )

        # 7. Fallback Estructural Local con PIL
        fallback_desc = self._local_structural_analysis(img_bytes, width, height, img_format, instruction)
        return VisionAnalysisResult(
            is_success=True,
            description=fallback_desc,
            engine_used="PIL Local Metadata & Heuristic Analyzer",
            image_path=str(image_path),
            width=width,
            height=height,
            format=img_format
        )

    def _try_ollama_vision(self, raw_b64: str, prompt: str) -> Optional[str]:
        """Intenta inferencia visual local con moondream o llava en Ollama."""
        candidate_prefixes = ["moondream", "llava", "qwen2-vl", "llama3.2-vision", "minicpm-v"]
        
        # Verificar qué modelos tiene Ollama actualmente
        installed_models = []
        try:
            req = urllib.request.Request(f"{self.ollama_base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    installed_models = [m["name"] for m in data.get("models", [])]
        except Exception:
            return None

        target_model = None
        for cand in candidate_prefixes:
            for inst in installed_models:
                if inst.startswith(cand) or cand in inst:
                    target_model = inst
                    break
            if target_model:
                break

        if not target_model:
            return None

        try:
            url = f"{self.ollama_base_url}/api/generate"
            payload = {
                "model": target_model,
                "prompt": prompt,
                "images": [raw_b64],
                "stream": False
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=45.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data.get("response", "")
        except Exception as e:
            print(f"[Ollama Vision Error]: {e}")
            pass

        return None

    def _try_fcc_proxy_vision(self, raw_b64: str, prompt: str, img_format: str) -> Optional[str]:
        """Envía la imagen a Free Claude Code proxy en http://127.0.0.1:8082."""
        fcc_url = "http://127.0.0.1:8082/v1/messages"
        media_type = f"image/{img_format.lower()}" if img_format.lower() in ("png", "jpeg", "webp", "gif") else "image/png"
        payload = {
            "model": "anthropic/ollama/qwen2.5-coder:7b",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": raw_b64
                            }
                        },
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        }
        try:
            req = urllib.request.Request(
                fcc_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "x-api-key": "freecc"}
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    for block in data.get("content", []):
                        if block.get("type") == "text":
                            return block.get("text")
        except Exception:
            pass
        return None

    def _try_gemini_vision(self, raw_b64: str, prompt: str, img_format: str) -> Optional[str]:
        """Invoca Google Gemini Vision API."""
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or getattr(default_config, "gemini_api_key", "")
        if not api_key:
            return None

        mime_type = "image/png"
        if img_format.lower() in ("jpg", "jpeg"):
            mime_type = "image/jpeg"
        elif img_format.lower() == "webp":
            mime_type = "image/webp"

        for model_name in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-pro"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": raw_b64
                                }
                            }
                        ]
                    }
                ]
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "")
            except Exception:
                continue
        return None

    def _try_openrouter_vision(self, raw_b64: str, prompt: str, img_format: str) -> Optional[str]:
        """Consulta modelos multimodales a través de OpenRouter."""
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            return None

        mime_type = f"image/{img_format.lower()}"
        data_url = f"data:{mime_type};base64,{raw_b64}"
        url = "https://openrouter.ai/api/v1/chat/completions"

        models = [
            "meta-llama/llama-3.2-11b-vision-instruct:free",
            "qwen/qwen-2-vl-72b-instruct:free",
            "google/gemini-2.0-flash-lite-preview-02-05:free"
        ]

        for model in models:
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
                    }
                ]
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/jev-agent"
                    }
                )
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "")
            except Exception:
                continue
        return None

    def _local_structural_analysis(
        self,
        img_bytes: bytes,
        width: int,
        height: int,
        img_format: str,
        instruction: str
    ) -> str:
        """Genera un análisis estructural y de características visuales básico mediante Pillow."""
        try:
            from PIL import Image, ImageStat
            with Image.open(io.BytesIO(img_bytes)) as img:
                stat = ImageStat.Stat(img)
                avg_r, avg_g, avg_b = [round(c, 1) for c in stat.mean[:3]]
                aspect_ratio = round(width / max(height, 1), 2)
                size_kb = round(len(img_bytes) / 1024, 1)

                is_landscape = width > height
                category = "Captura de pantalla o documento" if aspect_ratio > 1.3 else ("Fotografía o retrato" if aspect_ratio < 0.9 else "Gráfico cuadrado")

                return (
                    f"📷 **Análisis Estructural de Imagen Adjunta**:\n"
                    f"- **Dimensiones**: {width}x{height} píxeles (Relación de aspecto: {aspect_ratio}:1, {category}).\n"
                    f"- **Formato**: {img_format} ({size_kb} KB).\n"
                    f"- **Promedio de Color RGB**: R={avg_r}, G={avg_g}, B={avg_b}.\n"
                    f"- **Instrucción del Usuario**: '{instruction}'.\n\n"
                    f"*(Nota: Se aplicó análisis estructural de respaldo. La imagen se encuentra guardada y accesible para JEV)*"
                )
        except Exception as e:
            return f"Imagen cargada con éxito ({len(img_bytes)} bytes, {width}x{height} px). No se pudo extraer detalle cromático: {e}"
