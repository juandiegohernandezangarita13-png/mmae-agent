"""
Genera el catálogo de piezas de demostración del motor CAD de JEV.

Uso:
    .\.venv\Scripts\python.exe scripts\generate_cad_showcase.py

Escribe los archivos (OBJ/STL/GLB/GLTF + escena Three.js) en
workspace/cad_models/ y muestra un resumen de la geometría generada.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jev.tools.custom.skill_cad_mesh import ParametricCadMeshTool  # noqa: E402


SHOWCASE = {
    "Showcase_Gear": (
        "spur_gear",
        {"teeth": 26, "pitch_radius": 26, "thickness": 9, "bore_radius": 8,
         "hub_radius": 12, "hub_height": 7, "lightening_holes": 5,
         "hole_radius": 3.2, "hole_circle_radius": 17},
        "#00f0ff",
    ),
    "Showcase_Flange": (
        "flange",
        {"outer_radius": 32, "inner_radius": 12, "thickness": 7, "bolt_count": 6,
         "bolt_circle_radius": 24, "bolt_hole_radius": 2.6, "raised_face": 2},
        "#22d3ee",
    ),
    "Showcase_Enclosure": (
        "box_enclosure",
        {"width": 95, "depth": 62, "height": 30, "wall_thickness": 2.4,
         "corner_radius": 5, "lid": True, "standoffs": 4},
        "#a3e635",
    ),
    "Showcase_Bearing": (
        "bearing",
        {"outer_radius": 24, "inner_radius": 10, "width": 9, "ball_count": 9},
        "#f59e0b",
    ),
}


def main() -> int:
    tool = ParametricCadMeshTool()
    summary = []
    for name, (model_type, params, color) in SHOWCASE.items():
        result = tool.execute(
            model_type=model_type,
            name=name,
            parameters=params,
            color=color,
            quality="high",
        )
        if not result.success:
            print(f"[ERROR] {name}: {result.error}")
            continue
        data = result.data
        scene_path = Path(data["scene_path"])
        scene_path.write_text(json.dumps(data["scene"]), encoding="utf-8")
        summary.append({
            "name": name,
            "model_type": model_type,
            "vertices": data["vertex_count"],
            "triangles": data["face_count"],
            "volume_mm3": data["volume_mm3"],
            "watertight": data["watertight"],
            "files": sorted(data["files"]),
        })
        print(
            f"[OK] {name:20s} {model_type:14s} "
            f"{data['vertex_count']:6d} vértices / {data['face_count']:6d} triángulos  "
            f"vol={data['volume_mm3']:.1f} mm3  estanco={data['watertight']}"
        )

    print()
    print(f"Piezas generadas: {len(summary)}/{len(SHOWCASE)}")
    print(f"Carpeta de salida: {tool.workspace_dir / 'cad_models'}")
    return 0 if summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
