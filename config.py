import os
from pydantic import BaseModel

class AgentConfig(BaseModel):
    # Configuración de inferencia local
    api_base_url: str = os.getenv("MMAE_API_URL", "http://localhost:8000/v1")
    model_name: str = os.getenv("MMAE_MODEL", "local-model")
    
    # Parámetros del motor
    macro_temperature: float = 0.1
    micro_temperature: float = 0.2
    max_macro_tokens: int = 512
    max_micro_tokens: int = 1024
    
    # Parámetros del agente y seguridad
    max_history_turns: int = 20
    max_retries_per_step: int = 3
    terminal_timeout_seconds: int = 30
    safe_working_directory: str = os.getenv("MMAE_WORKSPACE", ".")

config = AgentConfig()
