"""
Handler para skill_web_design_pro en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_web_design_pro import WebDesignProTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = WebDesignProTool()
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
