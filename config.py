"""
Configuración unificada para MMAE (Macro-Micro Agent Engine) y JEV.
Proporciona soporte híbrido para inferencia local (llama.cpp, vLLM, LMStudio, Ollama)
y nubes avanzadas (OpenRouter, Gemini, Claude Code).
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR / "workspace"
MEMORY_DIR = BASE_DIR / "data" / "memory"
SCREENSHOTS_DIR = BASE_DIR / "data" / "screenshots"
CUSTOM_TOOLS_DIR = BASE_DIR / "jev" / "tools" / "custom"

# Asegurar directorios esenciales
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)

# Cargar variables de entorno desde .env si existe
env_file = BASE_DIR / ".env"
if env_file.exists():
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


@dataclass
class AgentConfig:
    # --- Parámetros de Inferencia MMAE (Macro-Micro) ---
    api_base_url: str = os.getenv(
        "MMAE_API_URL",
        os.getenv(
            "LMSTUDIO_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai"
            if os.getenv("GEMINI_API_KEY")
            else "http://localhost:8000/v1"
        )
    )
    model_name: str = os.getenv(
        "MMAE_MODEL",
        os.getenv(
            "JEV_MODEL",
            "gemini-flash-lite-latest"
            if os.getenv("GEMINI_API_KEY")
            else (
                "meta-llama/llama-3.3-70b-instruct:free"
                if os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENROUTER_API_KEY", "").startswith("sk-or-v1-dummy")
                else "local-model"
            )
        )
    )
    macro_temperature: float = float(os.getenv("MMAE_MACRO_TEMP", "0.1"))
    micro_temperature: float = float(os.getenv("MMAE_MICRO_TEMP", "0.2"))
    max_macro_tokens: int = int(os.getenv("MMAE_MAX_MACRO_TOKENS", "512"))
    max_micro_tokens: int = int(os.getenv("MMAE_MAX_MICRO_TOKENS", "1024"))
    max_tokens: int = int(os.getenv("JEV_MAX_TOKENS", "2048"))
    terminal_timeout_seconds: int = int(os.getenv("MMAE_TERMINAL_TIMEOUT", "30"))
    safe_working_directory: str = os.getenv("MMAE_WORKSPACE", str(WORKSPACE_DIR))

    # --- Parámetros del Agente Autónomo y Seguridad ---
    max_history_turns: int = int(os.getenv("MMAE_MAX_HISTORY", "20"))
    max_retries_per_step: int = int(os.getenv("MMAE_MAX_RETRIES", "3"))
    confirm_risky_actions: bool = os.getenv("JEV_CONFIRM_RISKY", "false").lower() in ("true", "1", "yes")
    safe_mode: bool = False
    max_iterations: int = int(os.getenv("JEV_MAX_ITERATIONS", "20"))
    temperature: float = 0.2

    # --- Proveedores de Inferencia y Conexiones ---
    llm_provider: str = os.getenv("JEV_LLM_PROVIDER", "gemini" if os.getenv("GEMINI_API_KEY") else "ollama")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    lmstudio_base_url: str = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    fcc_base_url: str = os.getenv("FCC_BASE_URL", "http://127.0.0.1:8082")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")

    # --- Modelos del Pipeline Híbrido ---
    thinker_model: str = os.getenv(
        "JEV_THINKER_MODEL",
        "gemini-flash-lite-latest" if os.getenv("GEMINI_API_KEY") else "meta-llama/llama-3.3-70b-instruct:free"
    )
    executor_model: str = os.getenv(
        "JEV_EXECUTOR_MODEL",
        "gemini-flash-lite-latest" if os.getenv("GEMINI_API_KEY") else "qwen2.5-coder:latest"
    )
    fcc_model: str = os.getenv("FCC_MODEL", "open_router/meta-llama/llama-3.3-70b-instruct:free")
    gemini_flash_pool: List[str] = field(default_factory=lambda: [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
    ])
    fallback_models: List[str] = field(default_factory=lambda: [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "deepseek/deepseek-r1:free",
        "deepseek/deepseek-chat:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
        "qwen2.5-coder:latest"
    ])
    use_free_model_cascade: bool = os.getenv("JEV_USE_FREE_CASCADE", "true").lower() in ("true", "1", "yes")
    hybrid_mode: bool = os.getenv("JEV_HYBRID_MODE", "true").lower() in ("true", "1", "yes")

    # --- Interfaz de Pantalla y Periféricos ---
    pyautogui_failsafe: bool = True
    screen_pause: float = 0.5

    # --- Interfaces: Telegram, Isla y Escritorio ---
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    allowed_telegram_user_id: int = int(os.getenv("ALLOWED_TELEGRAM_USER_ID", "0") or "0")
    island_mode: bool = True

    # --- Directorios del Sistema ---
    base_dir: Path = BASE_DIR
    workspace_dir: Path = WORKSPACE_DIR
    memory_dir: Path = MEMORY_DIR
    screenshots_dir: Path = SCREENSHOTS_DIR
    custom_tools_dir: Path = CUSTOM_TOOLS_DIR


# Instancias por defecto
default_config = AgentConfig()
config = default_config
