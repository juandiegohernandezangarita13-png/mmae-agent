"""
Handler para skill_hub_manager en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_hub_manager import SkillHubManagerTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = SkillHubManagerTool()
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
