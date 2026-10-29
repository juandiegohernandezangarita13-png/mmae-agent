import json
import re
from typing import Dict, Any, Optional

class ActionParser:
    """
    Parsea bloques de texto generados por el modelo para extraer comandos o llamadas
    a herramientas en formato JSON estructurado.
    """
    def __init__(self):
        # Busca bloques delimitados por ```json ... ``` o etiquetas <tool_call> ... </tool_call>
        self.json_block_pattern = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
        self.tag_pattern = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

    def extract_action(self, text: str) -> Optional[Dict[str, Any]]:
        # Intentar extraer desde etiqueta <tool_call>
        tag_match = self.tag_pattern.search(text)
        if tag_match:
            try:
                return json.loads(tag_match.group(1))
            except json.JSONDecodeError:
                pass

        # Intentar extraer desde bloque de código Markdown
        json_match = self.json_block_pattern.search(text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Búsqueda manual de la primera estructura de llaves { ... }
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None
