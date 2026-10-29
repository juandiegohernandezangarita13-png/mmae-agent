"""
Handler para skill_qa_auditor en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_qa_auditor import QAAuditorTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = QAAuditorTool()
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
