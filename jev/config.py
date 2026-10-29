"""
Adaptador de compatibilidad para jev.config importando la configuración unificada de MMAE.
"""
from config import (
    AgentConfig,
    default_config,
    config,
    BASE_DIR,
    WORKSPACE_DIR,
    MEMORY_DIR,
    SCREENSHOTS_DIR,
    CUSTOM_TOOLS_DIR
)

__all__ = [
    "AgentConfig",
    "default_config",
    "config",
    "BASE_DIR",
    "WORKSPACE_DIR",
    "MEMORY_DIR",
    "SCREENSHOTS_DIR",
    "CUSTOM_TOOLS_DIR"
]
