"""
Motor Autónomo de Generación de Imágenes para JEV.
Permite sintetizar imágenes de alta resolución directamente a partir de prompts textuales,
guardándolas localmente y retornando URIs base64 para renderizado instantáneo en el chat.
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error
import base64
import time
import os

from jev.config import BASE_DIR


@dataclass
class ImageGenerationResult:
    is_success: bool
    image_path: Optional[str] = None
    data_uri: Optional[str] = None
    markdown: str = ""
    prompt: str = ""
    error: Optional[str] = None
    dimensions: str = "1024x1024"


class ImageGeneratorService:
    """Servicio de generación de imágenes con soporte de modelos de vanguardia y fallback local."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or (Path(BASE_DIR) / "data" / "generated_images")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        model: str = "flux",
        enhance: bool = True
    ) -> ImageGenerationResult:
        """
        Genera una imagen a partir de un prompt utilizando la infraestructura de Pollinations AI (Flux/SDXL).
        Guarda el archivo en data/generated_images/ y genera un Data URI base64 para inserción inmediata en la UI.
        """
        if not prompt or not prompt.strip():
            return ImageGenerationResult(
                is_success=False,
                error="El prompt de generación de imagen no puede estar vacío."
            )

        clean_prompt = prompt.strip()
        encoded_prompt = urllib.parse.quote(clean_prompt)
        seed = int(time.time() * 1000) % 1000000

        # Endpoint optimizado con parámetros de calidad
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={width}&height={height}&model={model}&nologo=true&enhance={'true' if enhance else 'false'}&seed={seed}"
        )

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
                }
            )
            with urllib.request.urlopen(req, timeout=35.0) as resp:
                if resp.status != 200:
                    return ImageGenerationResult(
                        is_success=False,
                        error=f"Servicio de imagen respondió con código HTTP {resp.status}"
                    )
                image_bytes = resp.read()

            if not image_bytes or len(image_bytes) < 100:
                return ImageGenerationResult(
                    is_success=False,
                    error="Respuesta vacía o corrupta recibida del generador."
                )

            # Determinar extensión del archivo
            ext = ".png"
            mime_type = "image/png"
            if image_bytes.startswith(b"\xff\xd8"):
                ext = ".jpg"
                mime_type = "image/jpeg"
            elif image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
                ext = ".webp"
                mime_type = "image/webp"

            timestamp = int(time.time() * 1000)
            safe_filename = f"gen_{timestamp}{ext}"
            file_path = self.output_dir / safe_filename
            file_path.write_bytes(image_bytes)

            # Generar Data URI para visualización sin dependencias de servidor local
            b64_str = base64.b64encode(image_bytes).decode("ascii")
            data_uri = f"data:{mime_type};base64,{b64_str}"
            markdown_repr = f"![{clean_prompt}]({data_uri})"

            return ImageGenerationResult(
                is_success=True,
                image_path=str(file_path),
                data_uri=data_uri,
                markdown=markdown_repr,
                prompt=clean_prompt,
                dimensions=f"{width}x{height}"
            )

        except Exception as e:
            # Fallback garantizado en caso de timeout, desconexión de red o error de API
            return self._generate_fallback_banner(clean_prompt, width, height, error_msg=str(e))

    def _generate_fallback_banner(
        self,
        prompt: str,
        width: int,
        height: int,
        error_msg: str
    ) -> ImageGenerationResult:
        """Genera un banner local estilizado con PIL en caso de desconexión a internet."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            img = Image.new("RGB", (width, height), color=(15, 23, 42))
            draw = ImageDraw.Draw(img)

            # Cuadrícula cibernética decorativa
            for x in range(0, width, 40):
                draw.line([(x, 0), (x, height)], fill=(30, 41, 59), width=1)
            for y in range(0, height, 40):
                draw.line([(0, y), (width, y)], fill=(30, 41, 59), width=1)

            # Marco holográfico
            draw.rectangle([(20, 20), (width - 20, height - 20)], outline=(0, 240, 255), width=2)

            title = "JEV AI // VISUAL SYNTHESIS (OFFLINE FALLBACK)"
            draw.text((40, 50), title, fill=(0, 240, 255))
            draw.text((40, 100), f"Prompt: {prompt[:80]}", fill=(226, 232, 240))
            draw.text((40, 140), f"Alerta de red: {error_msg[:70]}", fill=(251, 191, 36))

            timestamp = int(time.time() * 1000)
            file_path = self.output_dir / f"fallback_{timestamp}.png"
            img.save(file_path, format="PNG")

            b64_str = base64.b64encode(file_path.read_bytes()).decode("ascii")
            data_uri = f"data:image/png;base64,{b64_str}"

            return ImageGenerationResult(
                is_success=True,
                image_path=str(file_path),
                data_uri=data_uri,
                markdown=f"![{prompt}]({data_uri})",
                prompt=prompt,
                dimensions=f"{width}x{height}",
                error=f"Generado con motor sintético local debido a: {error_msg}"
            )
        except Exception as e:
            return ImageGenerationResult(
                is_success=False,
                error=f"No se pudo generar la imagen ni el fallback local: {e}",
                prompt=prompt
            )
