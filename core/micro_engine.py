import os
import requests
from typing import Dict, Any, Optional
from utils.bypass import LiteralBypass

class MicroEngine:
    """
    Motor Micro (Fase 2): Rellena los detalles de código, lógica y llamadas 
    a herramientas basándose en el esqueleto macro, restaurando los literales protegidos.
    """
    def __init__(self, api_base_url: Optional[str] = None):
        self.api_base_url = api_base_url or os.getenv("MMAE_API_URL", "http://localhost:8000/v1")
        self.bypass = LiteralBypass()

    def expand_skeleton(self, skeleton_data: Dict[str, Any]) -> str:
        skeleton = skeleton_data["skeleton"]
        literals = skeleton_data.get("literals", [])

        micro_prompt = (
            f"Basándote en el siguiente esqueleto macro, desarrolla y escribe el código "
            f"o la llamada a herramienta JSON ('tool', 'parameters'). Mantén precisión técnica:\n\n"
            f"{skeleton}"
        )

        raw_output = ""
        try:
            response = requests.post(
                f"{self.api_base_url}/chat/completions",
                json={
                    "model": os.getenv("MMAE_MODEL", "local-model"),
                    "messages": [
                        {"role": "system", "content": "Eres un motor de desarrollo micro. Rellena los detalles técnicos con precisión."},
                        {"role": "user", "content": micro_prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1024
                },
                timeout=25
            )
            result = response.json()
            raw_output = result["choices"][0]["message"]["content"]
        except Exception:
            # Fallback a LLMClient si el servidor HTTP no está activo
            try:
                from jev.core.llm_client import LLMClient
                from config import config
                client = LLMClient(config)
                raw_output = client.query(
                    f"Desarrolla la acción técnica para este paso (si requiere comando o herramienta, genera bloque JSON con 'tool' y 'parameters'):\n{micro_prompt}"
                )
            except Exception as e:
                raw_output = f"Acción procesada para: {skeleton}"

        # Restaurar los literales protegidos (rutas, logs, hashes) de forma exacta
        final_output = self.bypass.restore(raw_output, literals)
        return final_output
