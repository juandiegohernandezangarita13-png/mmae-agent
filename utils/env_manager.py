import os
from typing import Dict, Optional

class EnvironmentManager:
    """
    Gestiona variables de entorno y configuración sensible de manera segura.
    """
    @staticmethod
    def get_var(key: str, default: Optional[str] = None) -> str:
        value = os.getenv(key, default)
        if value is None:
            raise KeyError(f"Variable de entorno obligatoria '{key}' no definida.")
        return value

    @staticmethod
    def set_var(key: str, value: str):
        os.environ[key] = value

    @staticmethod
    def snapshot() -> Dict[str, str]:
        # Filtra variables sensibles antes de exponerlas al contexto del agente
        sensitive_keywords = ["KEY", "TOKEN", "SECRET", "PASSWORD"]
        safe_env = {}
        for k, v in os.environ.items():
            if any(word in k.upper() for word in sensitive_keywords):
                safe_env[k] = "********"
            else:
                safe_env[k] = v
        return safe_env
