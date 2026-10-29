"""
Módulo ACE (Agent Computer Environment / Sandbox Runner).
Proporciona un entorno seguro y contenido para la ejecución de comandos de consola
y código generado por agentes de IA, con prevención estricta de operaciones destructivas.
"""
from typing import Dict, Any, Optional, Tuple, List
import subprocess
import tempfile
import time
import sys
import os
import re
import argparse
from pathlib import Path


class AgentSandboxRunner:
    """Ejecutor de comandos y entorno de pruebas seguro para agentes autónomos."""

    # Comandos destructivos estrictamente bloqueados
    BLOCKED_PATTERNS = [
        r"\bformat\b",
        r"\bdiskpart\b",
        r"\bbcdedit\b",
        r"\breg\s+delete\b",
        r"\btakeown\b",
        r"\bicacls\s+[cC]:\\\b",
        r"\bshutdown\s+/[s|r|f]\b",
        r"rmdir\s+/[sS]\s+/[qQ]\s+[cC]:\\",
        r"del\s+/[sS|fF|qQ]+\s+[cC]:\\(?:windows|system32)",
        r":\(\)\s*\{.*?\}\s*;:",  # fork bomb
    ]

    # Directorios protegidos del sistema
    PROTECTED_DIRS = [
        Path("C:/Windows"),
        Path("C:/Windows/System32"),
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)")
    ]

    def __init__(self, workspace_dir: Optional[str] = None):
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir).resolve()
        else:
            self.workspace_dir = Path.cwd().resolve()

    def validate_command_safety(self, command: str) -> Tuple[bool, Optional[str]]:
        """Valida que un comando no contenga instrucciones destructivas para el sistema."""
        cmd_lower = command.lower()
        for pat in self.BLOCKED_PATTERNS:
            if re.search(pat, cmd_lower):
                return False, f"Comando bloqueado por seguridad: coincide con patrón destructivo '{pat}'."
        return True, None

    def run_command(self, command: str, timeout: int = 30, cwd: Optional[str] = None) -> Dict[str, Any]:
        """
        Ejecuta un comando en PowerShell/Shell capturando stdout, stderr y código de salida.
        Garantiza que la ejecución esté aislada y controlada por timeout.
        """
        is_safe, error_msg = self.validate_command_safety(command)
        if not is_safe:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": error_msg,
                "duration": 0.0,
                "blocked": True
            }

        target_cwd = Path(cwd).resolve() if cwd else self.workspace_dir
        if not target_cwd.exists():
            target_cwd.mkdir(parents=True, exist_ok=True)

        # En Windows usar powershell
        cmd_args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd_args,
                cwd=str(target_cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )
            duration = round(time.time() - start_time, 3)
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "duration": duration,
                "blocked": False
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Tiempo de ejecución excedido (Timeout de {timeout}s).",
                "duration": timeout,
                "blocked": False
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Error del sandbox: {str(e)}",
                "duration": round(time.time() - start_time, 3),
                "blocked": False
            }

    def run_python_code(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """Ejecuta un bloque de código Python en un archivo temporal aislado."""
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            python_bin = sys.executable
            start_time = time.time()
            proc = subprocess.run(
                [python_bin, tmp_path],
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )
            duration = round(time.time() - start_time, 3)
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "duration": duration,
                "blocked": False
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Timeout excedido ({timeout}s).",
                "duration": timeout,
                "blocked": False
            }
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ACE - Agent Computer Environment Sandbox Runner")
    parser.add_argument("--cmd", help="Comando de consola a ejecutar")
    parser.add_argument("--code", help="Código Python a ejecutar")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout en segundos")
    args = parser.parse_args()

    runner = AgentSandboxRunner()
    if args.cmd:
        res = runner.run_command(args.cmd, timeout=args.timeout)
        import json
        print(json.dumps(res, indent=2))
    elif args.code:
        res = runner.run_python_code(args.code, timeout=args.timeout)
        import json
        print(json.dumps(res, indent=2))
    else:
        parser.print_help()
