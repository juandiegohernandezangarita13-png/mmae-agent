import requests
from typing import Dict, Any, List
from utils.bypass import LiteralBypass

class MicroEngine:
    """
    Motor Micro (Fase 2): Rellena los detalles de código, lógica y llamadas 
    a herramientas basándose en el esqueleto macro, restaurando los literales protegidos.
    """
    def __init__(self, api_base_url: str = "http://localhost:8000/v1"):
        self.api_base_url = api_base_url
        self.bypass = LiteralBypass()

    def expand_skeleton(self, skeleton_data: Dict[str, Any]) -> str:
        skeleton = skeleton_data["skeleton"]
        literals = skeleton_data["literals"]

        micro_prompt = (
            f"Basándote en el siguiente esqueleto macro, desarrolla y escribe el código "
            f"o la solución detallada paso a paso. Mantén la precisión técnica:\n\n"
            f"{skeleton}"
        )

        try:
            response = requests.post(
                f"{self.api_base_url}/chat/completions",
                json={
                    "model": "local-model",
                    "messages": [
                        {"role": "system", "content": "Eres un motor de desarrollo micro. Rellena los detalles técnicos con precisión."},
                        {"role": "user", "content": micro_prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1024
                },
                timeout=45
            )
            result = response.json()
            raw_output = result["choices"][0]["message"]["content"]
        except Exception as e:
            raw_output = f"Error conectando con el backend local en fase micro: {str(e)}"

        # Restaurar los literales protegidos (rutas, logs, hashes) de forma exacta
        final_output = self.bypass.restore(raw_output, literals)
        return final_output
