"""
Handler para skill_web_builder en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from pathlib import Path
from jev.tools.skill_web_builder import WebBuilderTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = WebBuilderTool()
    res = tool.execute(**kwargs)
    if res.success:
        return {
            "status": "success",
            "html": res.data.get("html", ""),
            "title": res.data.get("title", ""),
            "file_path": res.data.get("file_path")
        }
    else:
        return {
            "status": "error",
            "error": res.error
        }
