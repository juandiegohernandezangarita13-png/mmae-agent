"""
Habilidad Procedural de Generación de Mallas y Escenas 3D para Three.js.
Genera especificaciones geométricas completas compatibles con WebGL / Three.js.
"""
from typing import Dict, Any, Optional, List
import math


def create_box(params: Dict[str, Any]) -> Dict[str, Any]:
    w = float(params.get("width", 2.0))
    h = float(params.get("height", 2.0))
    d = float(params.get("depth", 2.0))
    color = params.get("color", "#00f0ff")
    wireframe = bool(params.get("wireframe", False))

    return {
        "type": "mesh",
        "name": params.get("name", "Box_Mesh"),
        "geometry": {
            "type": "BoxGeometry",
            "parameters": {"width": w, "height": h, "depth": d}
        },
        "material": {
            "type": "MeshStandardMaterial",
            "color": color,
            "wireframe": wireframe,
            "roughness": float(params.get("roughness", 0.3)),
            "metalness": float(params.get("metalness", 0.7))
        },
        "position": params.get("position", [0, 0, 0]),
        "rotation": params.get("rotation", [0, 0, 0]),
        "scale": params.get("scale", [1, 1, 1])
    }


def create_cylinder(params: Dict[str, Any]) -> Dict[str, Any]:
    r_top = float(params.get("radiusTop", 1.0))
    r_bottom = float(params.get("radiusBottom", 1.0))
    h = float(params.get("height", 3.0))
    radial_segs = int(params.get("radialSegments", 32))
    color = params.get("color", "#ffaa00")

    return {
        "type": "mesh",
        "name": params.get("name", "Cylinder_Mesh"),
        "geometry": {
            "type": "CylinderGeometry",
            "parameters": {
                "radiusTop": r_top,
                "radiusBottom": r_bottom,
                "height": h,
                "radialSegments": radial_segs
            }
        },
        "material": {
            "type": "MeshStandardMaterial",
            "color": color,
            "roughness": float(params.get("roughness", 0.4)),
            "metalness": float(params.get("metalness", 0.6))
        },
        "position": params.get("position", [0, 0, 0]),
        "rotation": params.get("rotation", [0, 0, 0]),
        "scale": params.get("scale", [1, 1, 1])
    }


def create_sphere(params: Dict[str, Any]) -> Dict[str, Any]:
    radius = float(params.get("radius", 1.5))
    width_segs = int(params.get("widthSegments", 32))
    height_segs = int(params.get("heightSegments", 32))
    color = params.get("color", "#00ff88")

    return {
        "type": "mesh",
        "name": params.get("name", "Sphere_Mesh"),
        "geometry": {
            "type": "SphereGeometry",
            "parameters": {"radius": radius, "widthSegments": width_segs, "heightSegments": height_segs}
        },
        "material": {
            "type": "MeshStandardMaterial",
            "color": color,
            "roughness": float(params.get("roughness", 0.2)),
            "metalness": float(params.get("metalness", 0.8))
        },
        "position": params.get("position", [0, 0, 0]),
        "rotation": params.get("rotation", [0, 0, 0]),
        "scale": params.get("scale", [1, 1, 1])
    }


def create_torus(params: Dict[str, Any]) -> Dict[str, Any]:
    radius = float(params.get("radius", 1.8))
    tube = float(params.get("tube", 0.4))
    radial_segs = int(params.get("radialSegments", 24))
    tubular_segs = int(params.get("tubularSegments", 48))
    color = params.get("color", "#ff0077")

    return {
        "type": "mesh",
        "name": params.get("name", "Torus_Mesh"),
        "geometry": {
            "type": "TorusGeometry",
            "parameters": {
                "radius": radius,
                "tube": tube,
                "radialSegments": radial_segs,
                "tubularSegments": tubular_segs
            }
        },
        "material": {
            "type": "MeshStandardMaterial",
            "color": color,
            "roughness": float(params.get("roughness", 0.25)),
            "metalness": float(params.get("metalness", 0.85))
        },
        "position": params.get("position", [0, 0, 0]),
        "rotation": params.get("rotation", [0, 0, 0]),
        "scale": params.get("scale", [1, 1, 1])
    }


def create_plane(params: Dict[str, Any]) -> Dict[str, Any]:
    w = float(params.get("width", 10.0))
    h = float(params.get("height", 10.0))
    color = params.get("color", "#111827")

    return {
        "type": "mesh",
        "name": params.get("name", "Plane_Mesh"),
        "geometry": {
            "type": "PlaneGeometry",
            "parameters": {"width": w, "height": h}
        },
        "material": {
            "type": "MeshStandardMaterial",
            "color": color,
            "roughness": 0.9,
            "metalness": 0.1
        },
        "position": params.get("position", [0, -1.5, 0]),
        "rotation": params.get("rotation", [-math.pi / 2, 0, 0]),
        "scale": [1, 1, 1]
    }


def create_parametric_grid(params: Dict[str, Any]) -> Dict[str, Any]:
    size = float(params.get("size", 12.0))
    divisions = int(params.get("divisions", 12))
    color_center = params.get("colorCenterLine", "#00f0ff")
    color_grid = params.get("colorGrid", "#1e293b")

    return {
        "type": "grid_helper",
        "name": "Parametric_Grid",
        "parameters": {
            "size": size,
            "divisions": divisions,
            "colorCenterLine": color_center,
            "colorGrid": color_grid
        },
        "position": [0, -1.5, 0]
    }


def create_arrow_helper(params: Dict[str, Any]) -> Dict[str, Any]:
    dir_vec = params.get("dir", params.get("direction", [0, 1, 0]))
    origin_vec = params.get("origin", params.get("position", [0, 0, 0]))
    length = float(params.get("length", 3.0))
    color = params.get("color", "#00f0ff")
    head_length = float(params.get("headLength", 0.6))
    head_width = float(params.get("headWidth", 0.4))

    return {
        "type": "arrow_helper",
        "name": params.get("name", "Arrow_Helper"),
        "direction": dir_vec,
        "origin": origin_vec,
        "length": length,
        "color": color,
        "headLength": head_length,
        "headWidth": head_width
    }


def handle(shape: str = "box", params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Punto de entrada de la habilidad."""
    p = params or {}
    shape_lower = (shape or "box").lower()

    generators = {
        "box": create_box,
        "cube": create_box,
        "cylinder": create_cylinder,
        "sphere": create_sphere,
        "torus": create_torus,
        "plane": create_plane,
        "parametric_grid": create_parametric_grid,
        "arrow": create_arrow_helper,
        "arrow_helper": create_arrow_helper
    }

    if shape_lower == "composite_scene":
        # Genera una escena compuesta completa lista para renderizar
        meshes = [
            create_parametric_grid({"size": 14, "divisions": 14}),
            create_box({"position": [-2.2, 0, 0], "color": "#00f0ff", "roughness": 0.3}),
            create_sphere({"position": [0, 0, 0], "color": "#ffaa00", "radius": 1.2}),
            create_torus({"position": [2.5, 0, 0], "color": "#ff0077", "radius": 1.2, "tube": 0.3})
        ]
        return {
            "scene": {
                "background": "#050811",
                "ambient_light": {"color": "#ffffff", "intensity": 0.6},
                "directional_light": {"color": "#00f0ff", "intensity": 1.2, "position": [6, 12, 8]},
                "elements": meshes
            },
            "status": "success",
            "message": "Escena 3D compuesta generada exitosamente para Three.js"
        }

    generator = generators.get(shape_lower, create_box)
    element = generator(p)

    return {
        "scene": {
            "background": "#050811",
            "ambient_light": {"color": "#ffffff", "intensity": 0.7},
            "directional_light": {"color": "#ffffff", "intensity": 1.0, "position": [5, 10, 7]},
            "elements": [
                create_parametric_grid({}),
                element
            ]
        },
        "element": element,
        "status": "success",
        "message": f"Geometría procedural '{shape}' generada exitosamente."
    }
