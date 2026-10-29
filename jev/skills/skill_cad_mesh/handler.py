"""
Handler para skill_cad_mesh en el SkillRegistry de JEV.
"""
from typing import Dict, Any
from jev.tools.custom.skill_cad_mesh import ParametricCadMeshTool


def handle(**kwargs) -> Dict[str, Any]:
    """Punto de entrada modular para el SkillRegistry."""
    tool = ParametricCadMeshTool()
    res = tool.execute(**kwargs)
    if res.success and res.data:
        return {
            "status": "success",
            "name": res.data.get("name"),
            "model_type": res.data.get("model_type"),
            "vertex_count": res.data.get("vertex_count"),
            "face_count": res.data.get("face_count"),
            "volume_mm3": res.data.get("volume_mm3"),
            "watertight": res.data.get("watertight"),
            "engine": res.data.get("engine"),
            "files": res.data.get("files"),
            "scene": res.data.get("scene"),
            "scene_path": res.data.get("scene_path"),
        }
    return {
        "status": "error",
        "error": res.error or res.output
    }
