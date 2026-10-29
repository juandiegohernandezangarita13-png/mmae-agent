import re
from typing import Dict, Any, List

class LiteralBypass:
    """
    Canal de alta fidelidad (Bypass) para datos críticos de agentes (rutas, logs, hashes, JSONs).
    Aísla estos elementos para evitar alteraciones o pérdida de contexto.
    """
    def __init__(self):
        # Patrones para detectar rutas absolutas, hashes y errores comunes en consola
        self.patterns = {
            "file_paths": r"(?:[a-zA-Z]:[\\/]|/)(?:[\w.-]+[\\/])+[\w.-]+",
            "hashes": r"\b[0-9a-f]{7,40}\b",
            "error_logs": r"(?:Error|Exception|Traceback|FATAL):.*"
        }

    def extract_and_shield(self, text: str) -> Dict[str, Any]:
        shielded_data: List[str] = []
        
        def replace_match(match):
            shielded_data.append(match.group(0))
            return f"__LITERAL_TOKEN_{len(shielded_data) - 1}__"

        processed_text = text
        for key, pattern in self.patterns.items():
            processed_text = re.sub(pattern, replace_match, processed_text, flags=re.IGNORECASE)

        return {
            "clean_text": processed_text,
            "literals": shielded_data
        }

    def restore(self, text: str, literals: List[str]) -> str:
        restored_text = text
        for idx, literal in enumerate(literals):
            restored_text = restored_text.replace(f"__LITERAL_TOKEN_{idx}__", literal)
        return restored_text
