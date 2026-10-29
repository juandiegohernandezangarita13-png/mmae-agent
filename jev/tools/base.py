"""
Framework base para herramientas (Tool Framework) de JEV.
Permite definir herramientas modulares con esquemas JSON y validación.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
import json


@dataclass
class ToolResult:
    """Resultado devuelto por la ejecución de una herramienta."""
    success: bool
    output: str
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        if self.success:
            return str(self.output)
        return f"ERROR: {self.error or self.output}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "data": self.data
        }


class BaseTool(ABC):
    """Clase base abstracta para cualquier herramienta de JEV."""
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Ejecuta la herramienta con los parámetros proporcionados."""
        pass

    def get_openai_schema(self) -> Dict[str, Any]:
        """Genera el esquema estándar compatible con function calling de OpenAI/Ollama."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }


class ToolRegistry:
    """Registro central de herramientas del agente."""
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Registra una nueva herramienta."""
        self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> None:
        """Elimina una herramienta del registro."""
        if tool_name in self._tools:
            del self._tools[tool_name]

    def get(self, tool_name: str) -> Optional[BaseTool]:
        """Obtiene una herramienta por su nombre."""
        return self._tools.get(tool_name)

    def list_tools(self) -> List[BaseTool]:
        """Lista todas las herramientas registradas."""
        return list(self._tools.values())

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """Devuelve todas las herramientas en formato compatible con llamadas de función."""
        return [tool.get_openai_schema() for tool in self._tools.values()]

    def to_prompt_description(self) -> str:
        """
        Genera una descripción en texto legible de las herramientas
        para modelos que no soportan llamadas de función nativas.
        """
        descriptions = []
        for tool in self._tools.values():
            params = json.dumps(tool.parameters.get("properties", {}), indent=2, ensure_ascii=False)
            required = tool.parameters.get("required", [])
            desc = (
                f"- Herramienta: {tool.name}\n"
                f"  Descripción: {tool.description}\n"
                f"  Parámetros requeridos: {required}\n"
                f"  Esquema de parámetros:\n{params}\n"
            )
            descriptions.append(desc)
        return "\n".join(descriptions)

    def execute_call(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Ejecuta una herramienta validando estrictamente su esquema JSON
        (Structured Function Calling) antes de llamar a execute().
        """
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Herramienta desconocida: '{tool_name}'. Las disponibles son: {list(self._tools.keys())}"
            )

        if not isinstance(arguments, dict):
            return ToolResult(
                success=False,
                output="",
                error=f"Estructura inválida: los argumentos para '{tool_name}' deben ser un objeto JSON (dict), recibido: {type(arguments).__name__}."
            )

        # 1. Validación estricta de parámetros obligatorios
        required = tool.parameters.get("required", [])
        missing = [param for param in required if param not in arguments or arguments[param] is None]
        if missing:
            return ToolResult(
                success=False,
                output="",
                error=(
                    f"ESQUEMA INVÁLIDO para '{tool_name}': Faltan los parámetros requeridos {missing}. "
                    f"Esquema de propiedades esperadas: {json.dumps(tool.parameters.get('properties', {}), ensure_ascii=False)}"
                )
            )

        # 2. Validación de tipos básicos según el esquema
        properties = tool.parameters.get("properties", {})
        for param_name, param_val in arguments.items():
            if param_name in properties:
                expected_type = properties[param_name].get("type")
                if expected_type == "string" and not isinstance(param_val, str):
                    arguments[param_name] = str(param_val)
                elif expected_type == "integer" and not isinstance(param_val, int):
                    try:
                        arguments[param_name] = int(param_val)
                    except (ValueError, TypeError):
                        return ToolResult(
                            success=False,
                            output="",
                            error=f"Tipo inválido para '{param_name}' en '{tool_name}': Se esperaba integer, recibido {type(param_val).__name__}."
                        )
                elif expected_type == "array" and not isinstance(param_val, list):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Tipo inválido para '{param_name}' en '{tool_name}': Se esperaba una lista (array), recibido {type(param_val).__name__}."
                    )

        try:
            return tool.execute(**arguments)
        except TypeError as te:
            return ToolResult(
                success=False,
                output="",
                error=f"Parámetros malformados para {tool_name}: {str(te)}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Excepción al ejecutar {tool_name}: {str(e)}"
            )


def get_browser_operator_tool():
    """Obtiene e instancia la herramienta BrowserOperatorTool (Browser-Use Engine)."""
    from jev.tools.custom.skill_browser_use import BrowserOperatorTool
    return BrowserOperatorTool()


def get_skill_hub_manager_tool():
    """Obtiene e instancia la herramienta SkillHubManagerTool (Dynamic Skill Fetcher & Installer)."""
    from jev.tools.custom.skill_hub_manager import SkillHubManagerTool
    return SkillHubManagerTool()


def get_qa_auditor_tool():
    """Obtiene e instancia la herramienta QAAuditorTool (Giskard QA & Red-Teaming Suite)."""
    from jev.tools.custom.skill_qa_auditor import QAAuditorTool
    return QAAuditorTool()


def get_auto_launch_video_tool():
    """Obtiene e instancia la herramienta AutoLaunchVideoTool (Auto-Launch Video Engine)."""
    from jev.tools.custom.skill_video_creator import AutoLaunchVideoTool
    return AutoLaunchVideoTool()


def get_repo_planner_tool():
    """Obtiene e instancia la herramienta RepoPlannerTool (Plandex-Style Sandbox Engine)."""
    from jev.tools.custom.skill_repo_planner import RepoPlannerTool
    return RepoPlannerTool()


def get_sdlc_senior_tool():
    """Obtiene e instancia la herramienta SDLCSeniorTool (SDLC Senior Protocol & Checkpoints)."""
    from jev.tools.custom.skill_sdlc_senior import SDLCSeniorTool
    return SDLCSeniorTool()


def get_osint_toolkit_tool():
    """Obtiene e instancia la herramienta OSINTToolkitTool (OSINT Multi-Vector Investigator)."""
    from jev.tools.custom.skill_osint_toolkit import OSINTToolkitTool
    return OSINTToolkitTool()


def get_web_design_pro_tool():
    """Obtiene e instancia la herramienta WebDesignProTool (Anti-Generic Web Design Engine)."""
    from jev.tools.custom.skill_web_design_pro import WebDesignProTool
    return WebDesignProTool()


def get_claude_code_tool():
    """Obtiene e instancia la herramienta ClaudeCodeTool (Free-Claude-Code & OpenRouter Bridge)."""
    from jev.tools.custom.skill_claude_code import ClaudeCodeTool
    return ClaudeCodeTool()
