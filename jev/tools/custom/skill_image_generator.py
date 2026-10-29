"""
Herramienta de Generación de Imágenes de Alta Calidad para JEV.
Permite al agente generar imágenes fotorrealistas, diagramas, arte conceptual e ilustraciones
a partir de descripciones en lenguaje natural para mostrar directamente en el chat.
"""
from typing import Dict, Any
from jev.tools.base import BaseTool, ToolResult
from jev.core.image_generator import ImageGeneratorService


class ImageGeneratorTool(BaseTool):
    name = "skill_image_generator"
    description = (
        "Genera imágenes visuales de alta calidad a partir de un prompt descriptivo en lenguaje natural. "
        "Guarda el archivo en el disco y devuelve una imagen lista para renderizarse directamente en el chat. "
        "Úsala cuando el usuario te pida crear, dibujar, generar o diseñar una imagen, ilustración, arte o logo."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Descripción detallada en inglés o español de la imagen a generar."
            },
            "width": {
                "type": "integer",
                "description": "Ancho de la imagen en píxeles (por defecto: 1024).",
                "default": 1024
            },
            "height": {
                "type": "integer",
                "description": "Alto de la imagen en píxeles (por defecto: 1024).",
                "default": 1024
            },
            "model": {
                "type": "string",
                "description": "Modelo de síntesis ('flux', 'turbo'). Por defecto 'flux'.",
                "default": "flux"
            }
        },
        "required": ["prompt"]
    }

    def __init__(self):
        super().__init__()
        self.service = ImageGeneratorService()

    def execute(self, **kwargs) -> ToolResult:
        prompt = kwargs.get("prompt", "")
        width = int(kwargs.get("width", 1024))
        height = int(kwargs.get("height", 1024))
        model = kwargs.get("model", "flux")

        if not prompt or not prompt.strip():
            return ToolResult(
                success=False,
                output="",
                error="Debes proporcionar un 'prompt' descriptivo para generar la imagen."
            )

        res = self.service.generate(
            prompt=prompt,
            width=width,
            height=height,
            model=model
        )

        if not res.is_success:
            return ToolResult(
                success=False,
                output="",
                error=res.error or "Error desconocido durante la generación de imagen."
            )

        output_text = (
            f"🎨 **Imagen Generada con Éxito**:\n\n"
            f"{res.markdown}\n\n"
            f"- **Ruta local**: `{res.image_path}`\n"
            f"- **Resolución**: {res.dimensions}\n"
            f"- **Prompt**: *{res.prompt}*"
        )

        return ToolResult(
            success=True,
            output=output_text,
            data={
                "image_path": res.image_path,
                "data_uri": res.data_uri,
                "markdown": res.markdown,
                "prompt": res.prompt,
                "dimensions": res.dimensions
            }
        )
