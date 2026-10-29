import os
import requests
from typing import Dict, Any
from utils.bypass import LiteralBypass

class MacroEngine:
    """
    Motor Macro (Fase 1): Genera la estructura lógica, el esqueleto y los pasos 
    globales del agente de forma rápida antes de entrar al detalle micro.
    """
    def __init__(self, api_base_url: str = "http://localhost:8000/v1"):
        self.api_base_url = api_base_url
        self.bypass = LiteralBypass()

    def generate_skeleton(self, user_prompt: str) -> Dict[str, Any]:
        # 1. Aislar datos críticos (rutas, logs, hashes) mediante el bypass
        shielded = self.bypass.extract_and_shield(user_prompt)
        
        # 2. Construir el prompt macro para exigir un esqueleto estructurado
        macro_prompt = (
            f"Analiza la siguiente tarea y genera un esqueleto en bloques o "
            f"pasos lógicos estructurados (sin redactar el código final detallado):\n\n"
            f"{shielded['clean_text']}"
        )

        # 3. Llamada al backend local (compatible con OpenAI/llama.cpp/vLLM)
        try:
            response = requests.post(
                f"{self.api_base_url}/chat/completions",
                json={
                    "model": "local-model",
                    "messages": [
                        {"role": "system", "content": "Eres un motor de arquitectura macro. Devuelve solo pasos y estructura lógica."},
                        {"role": "user", "content": macro_prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 512
                },
                timeout=30
            )
            result = response.json()
            raw_skeleton = result["choices"][0]["message"]["content"]
        except Exception as e:
            raw_skeleton = f"Error conectando con el backend local: {str(e)}"

        # 4. Retornar el esqueleto y los literales protegidos para la siguiente fase
        return {
            "skeleton": raw_skeleton,
            "literals": shielded["literals"]
        }
