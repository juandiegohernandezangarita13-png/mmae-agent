"""
Herramientas de gestión y manipulación de archivos para JEV.
Permite leer, escribir, modificar y explorar archivos del sistema de forma segura.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import os
import shutil

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config
from jev.core.sandbox import ExecutionSandbox


def _resolve_path(path_str: str, base_workspace: Optional[Path] = None) -> Path:
    base = base_workspace or default_config.workspace_dir
    p = Path(path_str)
    if not p.is_absolute():
        # Si la ruta comienza explícitamente con "workspace", evitar duplicarla
        if p.parts and p.parts[0].lower() == "workspace":
            p = Path(*p.parts[1:])
        p = (base / p).resolve()
    return p


class ReadFileTool(BaseTool):
    """Lee el contenido de un archivo de texto."""
    name = "read_file"
    description = (
        "Lee el contenido de un archivo. Si la ruta es relativa, se busca dentro del workspace. "
        "Permite limitar líneas si el archivo es extenso."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta del archivo a leer."},
            "max_lines": {"type": "integer", "description": "Número máximo de líneas a leer (opcional)."}
        },
        "required": ["path"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, path: str, max_lines: Optional[int] = None, **kwargs) -> ToolResult:
        try:
            target = _resolve_path(path, self.workspace_dir)
            is_safe, error_msg = ExecutionSandbox.validate_path_safety(target, allow_read_only=True)
            if not is_safe:
                return ToolResult(success=False, output="", error=f"Bloqueo de seguridad: {error_msg}")
            if not target.exists():
                return ToolResult(success=False, output="", error=f"El archivo '{target}' no existe.")
            if not target.is_file():
                return ToolResult(success=False, output="", error=f"'{target}' es un directorio, no un archivo.")

            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            if max_lines and max_lines < total_lines:
                content = "".join(lines[:max_lines])
                note = f"\n[... Truncado. Mostrando {max_lines} de {total_lines} líneas ...]"
            else:
                content = "".join(lines)
                note = ""

            return ToolResult(
                success=True,
                output=f"--- Archivo: {target} ({total_lines} líneas) ---\n\n{content}{note}",
                data={"path": str(target), "total_lines": total_lines}
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error leyendo archivo {path}: {e}")


class WriteFileTool(BaseTool):
    """Crea o sobrescribe un archivo con nuevo contenido."""
    name = "write_file"
    description = (
        "Crea un archivo o sobrescribe su contenido por completo. "
        "Crea automáticamente los directorios padre si no existen."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta del archivo a escribir."},
            "content": {"type": "string", "description": "Contenido textual completo a guardar en el archivo."}
        },
        "required": ["path", "content"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        try:
            target = _resolve_path(path, self.workspace_dir)
            is_safe, error_msg = ExecutionSandbox.validate_path_safety(target, allow_read_only=False)
            if not is_safe:
                return ToolResult(success=False, output="", error=f"Bloqueo de seguridad: {error_msg}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)

            lines_count = len(content.splitlines())
            return ToolResult(
                success=True,
                output=f"Archivo guardado exitosamente: {target} ({lines_count} líneas, {len(content)} caracteres)."
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error escribiendo archivo {path}: {e}")


class PatchFileTool(BaseTool):
    """Reemplaza un bloque exacto de texto dentro de un archivo existente."""
    name = "patch_file"
    description = (
        "Reemplaza un bloque de texto exacto (target_content) por un nuevo texto (replacement_content) "
        "dentro de un archivo existente sin tener que sobrescribir todo el archivo."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta del archivo a modificar."},
            "target_content": {"type": "string", "description": "Texto exacto que se desea reemplazar."},
            "replacement_content": {"type": "string", "description": "Nuevo texto de reemplazo."}
        },
        "required": ["path", "target_content", "replacement_content"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, path: str, target_content: str, replacement_content: str, **kwargs) -> ToolResult:
        try:
            target = _resolve_path(path, self.workspace_dir)
            is_safe, error_msg = ExecutionSandbox.validate_path_safety(target, allow_read_only=False)
            if not is_safe:
                return ToolResult(success=False, output="", error=f"Bloqueo de seguridad: {error_msg}")
            if not target.exists() or not target.is_file():
                return ToolResult(success=False, output="", error=f"Archivo no encontrado: {target}")

            with open(target, "r", encoding="utf-8") as f:
                content = f.read()

            if target_content not in content:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"El bloque de texto especificado no se encontró en el archivo '{target}'."
                )

            count = content.count(target_content)
            new_content = content.replace(target_content, replacement_content, 1)

            with open(target, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(
                success=True,
                output=f"Archivo '{target}' parcheado exitosamente. (Ocurrencias encontradas: {count})."
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error al parchear archivo {path}: {e}")


class ListDirTool(BaseTool):
    """Lista los archivos y carpetas de un directorio."""
    name = "list_dir"
    description = "Lista los contenidos de una carpeta, indicando si son archivos o subcarpetas y sus tamaños."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Ruta del directorio a inspeccionar (opcional, por defecto el workspace)."
            }
        },
        "required": []
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, path: Optional[str] = None, **kwargs) -> ToolResult:
        try:
            target = _resolve_path(path, self.workspace_dir) if path else self.workspace_dir
            if not target.exists():
                return ToolResult(success=False, output="", error=f"Directorio no encontrado: {target}")
            if not target.is_dir():
                return ToolResult(success=False, output="", error=f"'{target}' es un archivo, no un directorio.")

            entries = []
            for item in sorted(target.iterdir()):
                if item.is_dir():
                    entries.append(f"[DIR]  {item.name}/")
                else:
                    size_kb = item.stat().st_size / 1024
                    entries.append(f"[FILE] {item.name} ({size_kb:.1f} KB)")

            output_str = f"Contenidos de '{target}':\n" + ("\n".join(entries) if entries else "(Directorio vacío)")
            return ToolResult(success=True, output=output_str)
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error listando directorio {path}: {e}")
