import os
import requests
from typing import Dict, Any, Optional
from utils.bypass import LiteralBypass

class MacroEngine:
    """
    Motor Macro (Fase 1): Genera la estructura lógica, el esqueleto y los pasos 
    globales del agente de forma rápida antes de entrar al detalle micro.
    """
    def __init__(self, api_base_url: Optional[str] = None):
        self.api_base_url = api_base_url or os.getenv("MMAE_API_URL", "http://localhost:8000/v1")
        self.bypass = LiteralBypass()

    def generate_skeleton(self, user_prompt: str) -> Dict[str, Any]:
        # 1. Aislar datos críticos (rutas, logs, hashes) mediante el bypass
        shielded = self.bypass.extract_and_shield(user_prompt)
        
        # 2. Construir el prompt macro para exigir un esqueleto estructurado
        macro_prompt = (
            f"Analiza la siguiente tarea y genera un esqueleto en bloques o "
            f"pasos lógicos estructurados numerados (sin redactar código final):\n\n"
            f"{shielded['clean_text']}"
        )

        # 3. Llamada al backend local (compatible con OpenAI/llama.cpp/vLLM) con fallback resiliente
        raw_skeleton = ""
        try:
            response = requests.post(
                f"{self.api_base_url}/chat/completions",
                json={
                    "model": os.getenv("MMAE_MODEL", "local-model"),
                    "messages": [
                        {"role": "system", "content": "Eres un motor de arquitectura macro. Devuelve solo pasos y estructura lógica numerada."},
                        {"role": "user", "content": macro_prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 512
                },
                timeout=15
            )
            result = response.json()
            raw_skeleton = result["choices"][0]["message"]["content"]
        except Exception:
            # Fallback a LLMClient de JEV/MMAE si está configurado
            try:
                from jev.core.llm_client import LLMClient
                from config import config
                client = LLMClient(config)
                raw_skeleton = client.query(
                    f"Genera solo un plan de pasos lógicos numerados (1. ..., 2. ...) para:\n{shielded['clean_text']}"
                )
            except Exception:
                raw_skeleton = f"1. Inspeccionar objetivo: {shielded['clean_text']}\n2. Ejecutar acción primaria\n3. Verificar y reportar resultados"

        # 4. Retornar el esqueleto y los literales protegidos para la siguiente fase
        return {
            "skeleton": raw_skeleton,
            "literals": shielded["literals"]
        }
