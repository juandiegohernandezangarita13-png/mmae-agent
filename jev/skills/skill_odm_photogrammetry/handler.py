"""
Handler para skill_odm_photogrammetry en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_odm import OdmPhotogrammetryTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = OdmPhotogrammetryTool()
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
