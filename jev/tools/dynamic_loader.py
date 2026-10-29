"""
Cargador dinámico y creador de herramientas en tiempo de ejecución para JEV.
Permite que la IA autogenere nuevas herramientas de software y las incorpore
inmediatamente a su propio repertorio cognitivo.
"""
from typing import Dict, Any, List, Type, Optional, Tuple
import importlib.util
import inspect
import sys
from pathlib import Path

from jev.tools.base import BaseTool, ToolRegistry, ToolResult
from jev.config import default_config


import ast
import re

PROTECTED_JEV_MODULES = {
    "jev.core", "jev.core.agent", "jev.core.memory", "jev.core.llm_client",
    "jev.config", "jev.tools.base", "jev.tools.code_runner"
}


class ToolSecurityASTValidator(ast.NodeVisitor):
    """
    Inspecciona el AST del código fuente de herramientas dinámicas antes de su persistencia o ejecución.
    Garantiza:
    1. Que defina explícitamente al menos una clase que herede de BaseTool.
    2. Prohíbe llamadas peligrosas (os.system, os.popen, APIs directas de ctypes/kernel).
    3. Prohíbe manipulación de sys.modules y redefinición/monkey-patching de módulos protegidos de JEV.
    """

    def __init__(self):
        self.has_basetool_subclass = False
        self.classes_found: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes_found.append(node.name)
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseTool":
                self.has_basetool_subclass = True
            elif isinstance(base, ast.Attribute) and base.attr == "BaseTool":
                self.has_basetool_subclass = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Detectar os.system, os.popen, os.spawn*, os.exec*
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                val_id = node.func.value.id
                if val_id == "os" and attr_name in ("system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe"):
                    raise ValueError(f"Patrón de riesgo bloqueado: llamada no autorizada a 'os.{attr_name}'. Use las herramientas estándar de ejecución.")
                if val_id in ("ctypes", "_winreg", "winreg") and attr_name in ("windll", "cdll", "oledll"):
                    raise ValueError(f"Patrón de riesgo bloqueado: acceso no supervisado a APIs del kernel mediante '{val_id}.{attr_name}'.")

        # Detectar llamadas directas a funciones importadas peligrosas (ej. system('...'))
        elif isinstance(node.func, ast.Name):
            if node.func.id in ("system", "popen"):
                raise ValueError(f"Patrón de riesgo bloqueado: invocación directa a '{node.func.id}'.")

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "os":
            for alias in node.names:
                if alias.name in ("system", "popen"):
                    raise ValueError(f"Importación de riesgo prohibida: 'from os import {alias.name}'.")
        if node.module and any(node.module == m or node.module.startswith(m + ".") for m in PROTECTED_JEV_MODULES):
            # Comprobar si se intenta importar para sobrescribir
            pass
        if node.module == "ctypes":
            raise ValueError("Importación de riesgo prohibida: no se permite uso de 'ctypes' en herramientas dinámicas.")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "ctypes":
                raise ValueError("Importación de riesgo prohibida: 'import ctypes' no está permitido en herramientas dinámicas.")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Detectar intentos de modificar sys.modules sobrescribiendo módulos protegidos de JEV
        for target in node.targets:
            if isinstance(target, ast.Subscript):
                if isinstance(target.value, ast.Attribute) and target.value.attr == "modules":
                    if isinstance(target.value.value, ast.Name) and target.value.value.id == "sys":
                        slice_node = target.slice
                        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                            mod_name = slice_node.value
                            if any(mod_name == m or mod_name.startswith(m + ".") for m in PROTECTED_JEV_MODULES):
                                raise ValueError(f"Patrón de riesgo bloqueado: intento de secuestro del módulo protegido '{mod_name}' en 'sys.modules'.")
            elif isinstance(target, ast.Attribute):
                # Detectar monkey-patching sobre módulos de JEV
                if isinstance(target.value, ast.Name) and target.value.id in ("agent", "memory", "config"):
                    raise ValueError(f"Patrón de riesgo bloqueado: intento de monkey-patching sobre '{target.value.id}.{target.attr}'.")
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        # Detectar eliminación de módulos protegidos de JEV en sys.modules
        for target in node.targets:
            if isinstance(target, ast.Subscript):
                if isinstance(target.value, ast.Attribute) and target.value.attr == "modules":
                    if isinstance(target.value.value, ast.Name) and target.value.value.id == "sys":
                        slice_node = target.slice
                        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                            mod_name = slice_node.value
                            if any(mod_name == m or mod_name.startswith(m + ".") for m in PROTECTED_JEV_MODULES):
                                raise ValueError(f"Patrón de riesgo bloqueado: intento de eliminación del módulo protegido '{mod_name}' de 'sys.modules'.")
        self.generic_visit(node)

    @classmethod
    def validate(cls, python_code: str) -> Tuple[bool, Optional[str]]:
        try:
            tree = ast.parse(python_code)
        except SyntaxError as se:
            return False, f"Error de sintaxis en el código: {se}"
        except Exception as e:
            return False, f"Error parseando AST: {e}"

        validator = cls()
        try:
            validator.visit(tree)
        except ValueError as ve:
            return False, str(ve)

        if not validator.has_basetool_subclass:
            return False, (
                "El código no define ninguna clase que herede explícitamente de 'BaseTool'. "
                f"Clases detectadas: {validator.classes_found or 'ninguna'}."
            )

        return True, None


class DynamicToolManager:
    """Gestiona la compilación, carga y registro de herramientas dinámicas."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.custom_dir = default_config.custom_tools_dir

    def load_all(self) -> List[str]:
        """Carga todas las herramientas existentes en la carpeta custom."""
        loaded_names = []
        for file in self.custom_dir.glob("*.py"):
            if file.name.startswith("__"):
                continue
            names = self._load_from_file(file)
            loaded_names.extend(names)
        return loaded_names

    def _load_from_file(self, file_path: Path) -> List[str]:
        loaded = []
        try:
            content = file_path.read_text(encoding="utf-8")
            is_safe, error_msg = ToolSecurityASTValidator.validate(content)
            if not is_safe:
                print(f"[DynamicToolManager] Archivo '{file_path.name}' descartado por seguridad AST: {error_msg}")
                return []
        except Exception as e:
            print(f"[DynamicToolManager] Error leyendo '{file_path.name}': {e}")
            return []

        module_name = f"jev.tools.custom.{file_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseTool) and obj is not BaseTool and obj.name:
                        tool_instance = obj()
                        self.registry.register(tool_instance)
                        loaded.append(tool_instance.name)
        except Exception as e:
            print(f"[DynamicToolManager] Error al cargar {file_path.name}: {e}")
        return loaded

    def create_and_register_tool(self, tool_filename: str, python_code: str) -> ToolResult:
        """Guarda un nuevo script de herramienta y la registra en caliente tras validación AST."""
        if not tool_filename.endswith(".py"):
            tool_filename += ".py"

        target_path = self.custom_dir / tool_filename

        # 1. Validación estricta con AST de Python antes de tocar el disco o el registro
        is_safe, error_msg = ToolSecurityASTValidator.validate(python_code)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Validación AST de seguridad fallida: {error_msg}"
            )

        # 2. Guardar en disco únicamente si superó la validación
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(python_code)
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error guardando script de herramienta en disco: {e}"
            )

        # 3. Cargar e incorporar al registro en memoria
        loaded = self._load_from_file(target_path)
        if loaded:
            return ToolResult(
                success=True,
                output=f"Nueva(s) herramienta(s) compilada(s) y registrada(s) con éxito: {', '.join(loaded)}.",
                data={"tools": loaded, "file": str(target_path)}
            )
        else:
            # Revertir archivo para no dejar artefactos huérfanos
            if target_path.exists():
                try:
                    target_path.unlink()
                except Exception:
                    pass
            return ToolResult(
                success=False,
                output="",
                error=f"No se pudo instanciar la clase de herramienta en memoria tras validación AST."
            )


class CreateCustomTool(BaseTool):
    """Herramienta que permite al agente crear e integrar nuevas herramientas a sí mismo."""
    name = "create_custom_tool"
    description = (
        "Crea una nueva herramienta en Python y la integra dinámicamente en el repertorio del agente. "
        "El código debe importar 'BaseTool', 'ToolResult' desde 'jev.tools.base' y definir una clase "
        "que herede de BaseTool con 'name', 'description', 'parameters' y 'execute(**kwargs)'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "tool_filename": {
                "type": "string",
                "description": "Nombre de archivo para el script (ej: 'qr_generator.py', 'pdf_reader.py')."
            },
            "python_code": {
                "type": "string",
                "description": "Código fuente completo de la herramienta en Python."
            }
        },
        "required": ["tool_filename", "python_code"]
    }

    def __init__(self, manager: DynamicToolManager):
        super().__init__()
        self.manager = manager

    def execute(self, tool_filename: str, python_code: str, **kwargs) -> ToolResult:
        return self.manager.create_and_register_tool(tool_filename, python_code)
