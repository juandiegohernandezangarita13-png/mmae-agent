"""
Handler para skill_repo_planner en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_repo_planner import RepoPlannerTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = RepoPlannerTool()
    res = tool.execute(**kwargs)
    if res.success:
        return {
            "status": "success",
            "summary": res.output,
            "data": res.data
        }
    return {
        "status": "error",
        "error": res.error,
        "data": res.data
    }
