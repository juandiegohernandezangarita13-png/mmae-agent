"""
Handler para skill_meshtastic_gateway en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_meshtastic import MeshtasticGatewayTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = MeshtasticGatewayTool()
    res = tool.execute(**kwargs)
    if res.success:
        return {
            "status": "success",
            "summary": res.output,
            "data": res.data
        }
    return {
        "status": "error",
        "error": res.error
    }
