from typing import Dict, Any
from utils.action_parser import ActionParser
from skills.base import SkillRegistry

class AgentExecutor:
    """
    Interpreta el resultado detallado del MicroEngine y ejecuta la Skill correspondiente.
    """
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self.parser = ActionParser()

    def process_and_execute(self, micro_output: str) -> Dict[str, Any]:
        action_data = self.parser.extract_action(micro_output)
        
        if not action_data:
            # Si no hay bloque de acción, se asume que es una respuesta conversacional
            return {
                "is_action": False,
                "success": True,
                "message": micro_output
            }

        tool_name = action_data.get("tool") or action_data.get("action")
        params = action_data.get("parameters") or action_data.get("params") or {}

        if not tool_name:
            return {
                "is_action": True,
                "success": False,
                "error": "No se especificó el nombre de la herramienta ('tool') en el bloque JSON."
            }

        try:
            execution_result = self.registry.execute(tool_name, **params)
            return {
                "is_action": True,
                "tool": tool_name,
                "success": execution_result.get("success", True) if isinstance(execution_result, dict) else True,
                "result": execution_result
            }
        except Exception as e:
            return {
                "is_action": True,
                "tool": tool_name,
                "success": False,
                "error": f"Fallo ejecutando {tool_name}: {str(e)}"
            }
