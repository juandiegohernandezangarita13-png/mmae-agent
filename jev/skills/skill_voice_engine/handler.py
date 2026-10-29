"""
Handler para skill_voice_engine en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_voice_engine import VoiceEngineTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = VoiceEngineTool()
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
