import subprocess
import shlex
from typing import Dict, Any

class SafeTerminalSkill:
    """
    Ejecutor seguro de comandos en terminal con timeout y lista de comandos bloqueados.
    """
    BLOCKED_COMMANDS = [
        "rm -rf /", ":(){ :|:& };:", "dd if=", "mkfs", "shutdown", "reboot"
    ]

    def __init__(self, default_timeout: int = 30):
        self.default_timeout = default_timeout

    def run(self, command: str) -> Dict[str, Any]:
        # Verificación contra comandos destructivos
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command:
                return {
                    "success": False,
                    "error": f"Comando bloqueado por seguridad: '{blocked}'",
                    "stdout": ""
                }

        try:
            # Ejecución controlada con captura de stdout/stderr y timeout estricto
            process = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.default_timeout
            )
            return {
                "success": process.returncode == 0,
                "stdout": process.stdout.strip(),
                "stderr": process.stderr.strip(),
                "returncode": process.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"El comando excedió el tiempo límite de {self.default_timeout}s.",
                "stdout": ""
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stdout": ""
            }
