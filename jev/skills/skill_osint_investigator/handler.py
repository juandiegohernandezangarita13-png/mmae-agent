"""
Handler para skill_osint_investigator en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_osint_toolkit import OSINTToolkitTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = OSINTToolkitTool()
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
