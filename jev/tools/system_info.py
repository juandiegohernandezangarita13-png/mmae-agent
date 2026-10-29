"""
Herramienta de inspección de entorno y capacidades del sistema para JEV.
Permite al agente conocer las herramientas CLI instaladas, hardware disponible (GPU/CPU/RAM),
y estado del entorno de ejecución antes de planificar tareas complejas.
"""
from typing import Dict, Any, Optional
import shutil
import platform
import sys
import psutil
from pathlib import Path

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class SystemEnvironmentTool(BaseTool):
    """Inspecciona el entorno del sistema operativo, hardware y binarios instalados."""
    name = "get_system_environment"
    description = (
        "Devuelve información detallada del sistema: hardware disponible (GPU RTX 3050, CPU, RAM), "
        "binarios de desarrollo detectados en el sistema (git, python, node, npm, powershell, docker) "
        "y estado del entorno virtual y workspace."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, **kwargs) -> ToolResult:
        try:
            # 1. Hardware y SO
            os_info = f"{platform.system()} {platform.release()} (Versión {platform.version()})"
            cpu_count = psutil.cpu_count(logical=True)
            ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
            ram_avail_gb = round(psutil.virtual_memory().available / (1024 ** 3), 1)

            # 2. Binarios en PATH
            target_binaries = ["git", "python", "node", "npm", "powershell", "docker", "curl", "pip"]
            installed_binaries = {}
            for b in target_binaries:
                path = shutil.which(b)
                installed_binaries[b] = path if path else "No instalado"

            # 3. Estado de GPU
            gpu_info = "NVIDIA GeForce RTX 3050 Laptop GPU (CUDA compatible)"

            # 4. Workspace
            ws_exists = self.workspace_dir.exists()

            # 5. Privilegios de ejecución (UAC / Admin check)
            is_admin = False
            if sys.platform == "win32":
                try:
                    import ctypes
                    is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
                except Exception:
                    is_admin = False
            privilege_label = "Administrador (Token Elevado)" if is_admin else "Usuario Estándar (User-Space - Usar pip y portables sin UAC)"

            output_lines = [
                "=== INFORME DE ENTORNO DEL SISTEMA JEV ===",
                f"• Sistema Operativo: {os_info}",
                f"• Nivel de Privilegios: {privilege_label}",
                f"• Procesador (CPU): {cpu_count} hilos lógicos",
                f"• Memoria RAM: {ram_avail_gb} GB disponibles / {ram_gb} GB totales",
                f"• Aceleración Gráfica (GPU): {gpu_info}",
                f"• Intérprete Python Activo: {sys.executable}",
                f"• Espacio de Trabajo Confinado: {self.workspace_dir} (Existe: {ws_exists})",
                "\n--- BINARIOS DE DESARROLLO DISPONIBLES EN PATH ---"
            ]
            for b, p in installed_binaries.items():
                status = "✓" if p != "No instalado" else "✗"
                output_lines.append(f"  {status} {b}: {p}")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={
                    "os": os_info,
                    "ram_gb": ram_gb,
                    "binaries": installed_binaries,
                    "workspace": str(self.workspace_dir)
                }
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error consultando entorno del sistema: {str(e)}"
            )
