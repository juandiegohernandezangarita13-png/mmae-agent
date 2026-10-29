"""
Handler para skill_combinatorial_analytics en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_combinatorial_analytics import CombinatorialAnalyticsTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = CombinatorialAnalyticsTool()
    res = tool.execute(**kwargs)
    if res.success:
        return {
            "status": "success",
            "summary": res.output,
            "data": res.data
        }
    else:
        return {
            "status": "error",
            "error": res.error
        }
