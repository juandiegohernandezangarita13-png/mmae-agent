"""
Handler para skill_frigate_vision_bridge en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_frigate import FrigateVisionBridgeTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = FrigateVisionBridgeTool()
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
