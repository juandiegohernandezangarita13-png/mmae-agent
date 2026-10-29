"""
Handler para skill_browser_operator en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_browser_use import BrowserOperatorTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = BrowserOperatorTool()
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
