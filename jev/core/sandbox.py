"""
Sandbox de Ejecución y Entorno de Terminal Seguro para JEV.
Previene operaciones destructivas accidentales y controla los límites de seguridad
del sistema de archivos y comandos de PowerShell en Windows.
"""
from typing import Tuple, List, Optional
import re
from pathlib import Path

from jev.config import default_config


class SandboxSecurityError(Exception):
    """Excepción lanzada cuando un comando viola las políticas de seguridad del Sandbox."""
    pass


class ExecutionSandbox:
    """Validador y protector de entorno seguro para comandos y rutas."""

    # Comandos destructivos estrictamente bloqueados en Windows
    BLOCKED_COMMAND_PATTERNS = [
        r"\bformat(?:\.com)?\s+[a-zA-Z]:",
        r"\bformat(?:\.com)?\s+/[a-zA-Z]",
        r"\bdiskpart\b",
        r"\bbcdedit\b",
        r"\breg\s+delete\b",
        r"\btakeown\b",
        r"\bicacls\s+c:\\\b",
        r"\bshutdown\s+/[s|r|f]\b",
        r"rmdir\s+/[sS]\s+/[qQ]\s+[cC]:\\",
        r"del\s+/[sS|fF|qQ]+\s+[cC]:\\(?:windows|system32)",
        r":\(\)\s*\{.*?\}\s*;:",  # fork bomb
    ]

    # Directorios protegidos del sistema que nunca deben ser modificados
    PROTECTED_SYSTEM_DIRS = [
        Path("C:/Windows"),
        Path("C:/Windows/System32"),
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
    ]

    @classmethod
    def validate_command(cls, command: str) -> Tuple[bool, Optional[str]]:
        """
        Analiza si el comando contiene patrones peligrosos o destructivos.
        Retorna (is_safe, error_message).
        """
        cmd_lower = command.lower()

        for pattern in cls.BLOCKED_COMMAND_PATTERNS:
            if re.search(pattern, cmd_lower):
                return False, f"Comando bloqueado por el Sandbox de seguridad: coincide con patrón peligroso '{pattern}'."

        return True, None

    @classmethod
    def validate_path_safety(cls, target_path: Path, allow_read_only: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Comprueba que una ruta no apunte a directorios críticos del sistema operativo.
        """
        try:
            resolved = target_path.resolve()
            for protected in cls.PROTECTED_SYSTEM_DIRS:
                try:
                    if resolved == protected.resolve() or protected.resolve() in resolved.parents:
                        if not allow_read_only:
                            return False, f"Acceso restringido: No se permite modificar el directorio del sistema '{protected}'."
                except Exception:
                    pass
            return True, None
        except Exception as e:
            return False, f"Error validando ruta segura: {e}"
