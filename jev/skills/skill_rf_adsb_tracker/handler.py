"""
Handler para skill_rf_adsb_tracker en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_rf_adsb import RFAdsbTrackerTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = RFAdsbTrackerTool()
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
