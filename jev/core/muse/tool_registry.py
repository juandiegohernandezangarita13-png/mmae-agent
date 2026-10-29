"""
Registro Desacoplado de Herramientas (Tool Registry) para Muse Spark en JEV.
Permite registrar y gestionar:
1. Invocaciones a subprocesos del sistema operativo (PowerShell en Windows / Bash en Linux).
2. Funciones nativas de Python (síncronas o asíncronas) con introspección de parámetros.
3. Herramientas heredadas derivadas de BaseTool de JEV.
"""
from typing import Dict, Any, Callable, Optional, List, Union
import inspect
import json
import logging
from dataclasses import dataclass, field

from jev.tools.base import BaseTool

logger = logging.getLogger("jev.muse.tool_registry")


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]
    is_shell_command: bool = False
    is_async: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """
    Registro centralizado y desacoplado de herramientas para el motor de ejecución.
    Proporciona serialización de esquemas para el LLM y resolución dinámica de invocaciones.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register_function(
        self,
        name: str,
        func: Callable[..., Any],
        description: Optional[str] = None,
        parameters_schema: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Registra una función Python nativa. Si no se suministra schema,
        se infiere automáticamente mediante introspección de type hints y docstrings.
        """
        doc = description or inspect.getdoc(func) or f"Función Python nativa {name}."
        schema = parameters_schema or self._generate_param_schema_from_callable(func)
        is_async = inspect.iscoroutinefunction(func)

        self._tools[name] = ToolDefinition(
            name=name,
            description=doc,
            parameters=schema,
            handler=func,
            is_shell_command=False,
            is_async=is_async,
            metadata=metadata or {}
        )
        logger.debug(f"Herramienta Python '{name}' registrada en ToolRegistry.")

    def register_shell_command(
        self,
        name: str = "shell_command",
        description: str = "Ejecuta comandos de consola en el sistema operativo (PowerShell en Windows / Bash en POSIX).",
        parameters_schema: Optional[Dict[str, Any]] = None,
        custom_runner: Optional[Callable[..., Any]] = None
    ) -> None:
        """Registra un punto de entrada para ejecución de scripts y comandos de consola del sistema."""
        schema = parameters_schema or {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Comando o script de terminal a ejecutar."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Tiempo límite en segundos (por defecto 60s).",
                    "default": 60
                }
            },
            "required": ["command"]
        }

        # Runner por defecto si no se inyecta uno específico
        handler = custom_runner or (lambda command, timeout=60, **kwargs: (command, timeout))

        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=schema,
            handler=handler,
            is_shell_command=True,
            is_async=False,
            metadata={"type": "system_subprocess"}
        )
        logger.debug(f"Herramienta Shell Subprocess '{name}' registrada.")

    def register_base_tool(self, tool_instance: BaseTool) -> None:
        """Adapta y registra una herramienta existente que herede de BaseTool de JEV."""
        name = getattr(tool_instance, "name", tool_instance.__class__.__name__)
        doc = getattr(tool_instance, "description", inspect.getdoc(tool_instance) or "")
        params = getattr(tool_instance, "parameters", {"type": "object", "properties": {}})

        self._tools[name] = ToolDefinition(
            name=name,
            description=doc,
            parameters=params,
            handler=tool_instance.execute,
            is_shell_command=False,
            is_async=False,
            metadata={"source": "BaseTool", "class": tool_instance.__class__.__name__}
        )
        logger.debug(f"BaseTool '{name}' registrada en ToolRegistry.")

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Obtiene la definición de una herramienta por su nombre."""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Verifica si una herramienta existe en el registro."""
        return name in self._tools

    def list_tools(self) -> List[str]:
        """Retorna los nombres de todas las herramientas registradas."""
        return list(self._tools.keys())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Retorna las especificaciones de todas las herramientas en formato JSON Schema."""
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            })
        return schemas

    def get_schema_text(self) -> str:
        """Formatea las herramientas registradas en texto estructurado para el System Prompt."""
        lines = []
        for tool in self._tools.values():
            lines.append(f"- `{tool.name}`: {tool.description}")
            props = tool.parameters.get("properties", {})
            required = tool.parameters.get("required", [])
            if props:
                lines.append("  Parámetros:")
                for p_name, p_info in props.items():
                    req_mark = " (Requerido)" if p_name in required else " (Opcional)"
                    desc = p_info.get("description", p_info.get("type", "any"))
                    lines.append(f"    * `{p_name}`{req_mark}: {desc}")
        return "\n".join(lines) if lines else "(No hay herramientas externas registradas)"

    def _generate_param_schema_from_callable(self, func: Callable) -> Dict[str, Any]:
        """Infiere el esquema JSON de parámetros desde la firma de la función."""
        sig = inspect.signature(func)
        properties = {}
        required = []

        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }

        for p_name, param in sig.parameters.items():
            if p_name in ("self", "cls", "kwargs", "args"):
                continue

            param_type = "string"
            if param.annotation != inspect.Parameter.empty and param.annotation in type_map:
                param_type = type_map[param.annotation]

            prop_def: Dict[str, Any] = {"type": param_type}
            if param.default != inspect.Parameter.empty:
                prop_def["default"] = param.default
            else:
                required.append(p_name)

            properties[p_name] = prop_def

        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
