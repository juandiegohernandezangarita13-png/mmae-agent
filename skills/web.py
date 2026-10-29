import requests
from typing import Dict, Any

class SafeWebSkill:
    """
    Herramienta segura de peticiones HTTP con control de timeout y tamaño de respuesta.
    """
    def __init__(self, timeout: int = 15, max_chars: int = 4000):
        self.timeout = timeout
        self.max_chars = max_chars

    def fetch_url(self, url: str) -> Dict[str, Any]:
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            text = response.text[:self.max_chars]
            return {
                "success": True,
                "status_code": response.status_code,
                "content": text
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Fallo al consultar URL '{url}': {str(e)}"
            }
