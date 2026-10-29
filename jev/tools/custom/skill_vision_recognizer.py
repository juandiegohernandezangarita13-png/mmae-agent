"""
Herramienta de Reconocimiento Visual y Análisis Multimodal para JEV.
Permite inspeccionar, transcribir y explicar imágenes, capturas de pantalla, diagramas y documentos.
"""
from typing import Dict, Any
from jev.tools.base import BaseTool, ToolResult
from jev.core.vision_engine import VisionEngine


class VisionRecognizerTool(BaseTool):
    name = "skill_vision_recognizer"
    description = (
        "Analiza, reconoce e interpreta el contenido visual de imágenes, fotografías, capturas de pantalla, "
        "diagramas de arquitectura, interfaces gráficas o texto manuscrito. "
        "Úsala para responder preguntas sobre imágenes, depurar errores mostrados en capturas de pantalla, "
        "leer diagramas o describir objetos."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Ruta absoluta o relativa del archivo de imagen a inspeccionar, o cadena base64 Data URI."
            },
            "instruction": {
                "type": "string",
                "description": "Pregunta específica o instrucción sobre lo que se debe analizar o extraer de la imagen.",
                "default": "Describe detalladamente lo que ves en esta imagen y transcribe cualquier texto relevante."
            }
        },
        "required": ["image_path"]
    }

    def __init__(self):
        super().__init__()
        self.engine = VisionEngine()

    def execute(self, **kwargs) -> ToolResult:
        image_path = (
            kwargs.get("image_path")
            or kwargs.get("image_data")
            or kwargs.get("image")
            or ""
        )
        instruction = (
            kwargs.get("instruction")
            or kwargs.get("prompt")
            or kwargs.get("question")
            or ""
        )

        if not image_path or not image_path.strip():
            return ToolResult(
                success=False,
                output="",
                error="Debes proporcionar 'image_path' con la ruta del archivo de imagen."
            )

        res = self.engine.analyze(
            image_source=image_path.strip(),
            user_prompt=instruction
        )

        if not res.is_success:
            return ToolResult(
                success=False,
                output="",
                error=res.error or "Error desconocido al procesar la imagen."
            )

        output_text = (
            f"🔍 **Análisis Visual Completado** ({res.engine_used}):\n\n"
            f"{res.description}\n\n"
            f"- **Dimensiones**: {res.width}x{res.height} px ({res.format})\n"
            f"- **Archivo**: `{res.image_path}`"
        )

        return ToolResult(
            success=True,
            output=output_text,
            data={
                "description": res.description,
                "engine_used": res.engine_used,
                "image_path": res.image_path,
                "width": res.width,
                "height": res.height,
                "format": res.format
            }
        )
