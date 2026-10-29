"""
Habilidad de Modelado 3D Paramétrico y Pipeline CAD de JEV.

Genera geometría de ingeniería REAL (sólidos estancos con taladros, vaciados,
chaflanes y operaciones booleanas) sobre el kernel cad_kernel y la proyecta en
el Viewport Three.js en vivo, además de exportar a los formatos estándar de
intercambio y fabricación digital:

1. Escena Three.js JSON con BufferGeometry real (vértices + índices) para el
   Viewport holográfico.
2. Wavefront .OBJ para herramientas CAD/CAM.
3. .STL binario (impresión 3D) y .GLB binario (motores web, Blender, visores).
4. .GLTF 2.0 embebido en Base64 (compatibilidad universal).
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import base64
import json
import math
import re

import numpy as np

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config
from jev.core import cad_kernel as kernel


PART_ENUM = kernel.list_part_types()


class ParametricCadMeshTool(BaseTool):
    """Herramienta de generación, exportación y proyección de piezas CAD."""

    name = "skill_cad_mesh"
    description = (
        "Genera piezas 3D de ingeniería con geometría real (sólidos estancos con taladros y booleanas) "
        "y las proyecta en el Viewport 3D en vivo. Piezas soportadas: "
        "spur_gear (engranaje recto), helical_gear (engranaje helicoidal), flange (brida con pernos), "
        "washer, hex_nut, bolt (perno con cabeza hexagonal), shaft (eje con chavetero), "
        "box_enclosure (carcasa hueca), l_bracket (escuadra), pulley (polea), bearing (rodamiento), "
        "gear_rack (cremallera), plate (placa con taladros), pipe_elbow (codo), helical_spring (resorte), "
        "box y cylinder. Exporta OBJ, STL, GLB y GLTF."
    )
    parameters = {
        "type": "object",
        "properties": {
            "model_type": {
                "type": "string",
                "description": (
                    "Tipo de pieza a generar. Ejemplos: 'spur_gear', 'flange', 'box_enclosure', "
                    "'hex_nut', 'bolt', 'pulley', 'l_bracket', 'pipe_elbow', 'helical_spring'."
                ),
                "enum": PART_ENUM,
                "default": "spur_gear"
            },
            "name": {
                "type": "string",
                "description": "Nombre identificador de la pieza (ej. 'Motor_Pinion_Gear').",
                "default": "CAD_Part"
            },
            "parameters": {
                "type": "object",
                "description": (
                    "Parámetros dimensionales de la pieza. Engranaje: teeth, pitch_radius, thickness, bore_radius, "
                    "tooth_height, hub_radius, lightening_holes. Brida: outer_radius, inner_radius, thickness, "
                    "bolt_count, bolt_circle_radius, bolt_hole_radius, raised_face. Carcasa: width, depth, height, "
                    "wall_thickness, corner_radius, lid, standoffs. Tuerca: across_flats, thickness, bore_radius. "
                    "Perno: head_diameter, head_height, shank_diameter, length. Polea: outer_radius, groove_depth, "
                    "width, bore_radius. Escuadra: leg_a, leg_b, width, thickness, hole_diameter. "
                    "Codo: radius, bend_radius, angle_deg. Resorte: coil_radius, wire_radius, turns, pitch."
                ),
                "default": {}
            },
            "export_formats": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Formatos de exportación: 'obj', 'stl', 'glb', 'gltf'. Por defecto todos.",
                "default": ["obj", "stl", "glb", "gltf"]
            },
            "color": {
                "type": "string",
                "description": "Color hexadecimal para el material del Viewport (ej. '#00f0ff').",
                "default": "#00f0ff"
            },
            "quality": {
                "type": "string",
                "description": "Resolución de teselado: 'low', 'medium' o 'high'.",
                "enum": ["low", "medium", "high"],
                "default": "medium"
            }
        },
        "required": ["model_type"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = Path(workspace_dir) if workspace_dir else default_config.workspace_dir

    # ------------------------------------------------------------------
    # EJECUCIÓN
    # ------------------------------------------------------------------
    def execute(
        self,
        model_type: str = "spur_gear",
        name: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        export_formats: Optional[List[str]] = None,
        color: str = "#00f0ff",
        quality: str = "medium",
        **kwargs: Any,
    ) -> ToolResult:
        try:
            key = kernel.normalize_model_type(model_type)
            display_name = re.sub(r"[^\w\-]+", "_", (name or f"CAD_{key}").strip())[:64] or f"CAD_{key}"

            # Tolerancia a modelos débiles: a veces envían 'parameters' como
            # string JSON y 'export_formats' como lista separada por comas.
            if isinstance(parameters, str):
                try:
                    parameters = json.loads(parameters)
                except (json.JSONDecodeError, TypeError):
                    parameters = {}
            params = dict(parameters or {})
            if isinstance(export_formats, str):
                export_formats = [f.strip() for f in export_formats.replace(";", ",").split(",") if f.strip()]
            params["quality"] = str(quality or "medium").lower()

            mesh, meta = kernel.build_part(key, params, name=display_name)

            output_dir = self.workspace_dir / "cad_models"
            output_dir.mkdir(parents=True, exist_ok=True)

            formats = [str(f).lower().strip() for f in (export_formats or ["obj", "stl", "glb", "gltf"])]
            files: Dict[str, str] = {}
            errors: List[str] = []

            if "obj" in formats:
                try:
                    path = output_dir / f"{display_name}.obj"
                    self.export_obj(mesh, path)
                    files["obj"] = str(path)
                except Exception as exc:
                    errors.append(f"OBJ: {exc}")
            if "stl" in formats:
                try:
                    path = output_dir / f"{display_name}.stl"
                    self.export_stl(mesh, path)
                    files["stl"] = str(path)
                except Exception as exc:
                    errors.append(f"STL: {exc}")
            if "glb" in formats:
                try:
                    path = output_dir / f"{display_name}.glb"
                    self.export_glb(mesh, path, color)
                    files["glb"] = str(path)
                except Exception as exc:
                    errors.append(f"GLB: {exc}")
            if "gltf" in formats:
                try:
                    path = output_dir / f"{display_name}.gltf"
                    self.export_gltf(mesh, path, color)
                    files["gltf"] = str(path)
                except Exception as exc:
                    errors.append(f"GLTF: {exc}")

            scene = self.build_viewport_scene(display_name, key, mesh, meta, color)
            scene_path = output_dir / f"{display_name}.scene.json"
            try:
                scene_path.write_text(json.dumps(scene, ensure_ascii=False), encoding="utf-8")
                files["scene"] = str(scene_path)
            except Exception as exc:
                errors.append(f"SCENE: {exc}")

            watertight = meta.get("watertight")
            msg = (
                f"Pieza CAD '{display_name}' ({key}) generada con geometría real: "
                f"{mesh.vertex_count} vértices, {mesh.face_count} triángulos, "
                f"volumen {meta['volume_mm3']:.2f} mm3"
                + (" (sólido estanco)" if watertight else "")
                + f". Motor: {meta['engine']}. Formatos: {sorted(k for k in files if k != 'scene')}. "
                "Modelo proyectado en el Viewport 3D."
            )
            if errors:
                msg += " Avisos: " + "; ".join(errors)

            return ToolResult(
                success=True,
                output=msg,
                data={
                    "name": display_name,
                    "model_type": key,
                    "vertex_count": mesh.vertex_count,
                    "face_count": mesh.face_count,
                    "volume_mm3": meta["volume_mm3"],
                    "watertight": watertight,
                    "engine": meta["engine"],
                    "units": "mm",
                    "bounds_mm": meta["bounds_mm"],
                    "files": files,
                    "scene": scene,
                    "scene_path": str(scene_path),
                    "export_errors": errors,
                },
            )
        except Exception as exc:  # noqa: BLE001 - se reporta al agente
            return ToolResult(
                success=False,
                output="",
                error=(
                    f"Error en el modelado paramétrico CAD de '{model_type}': {exc}. "
                    "Verifica los parámetros o usa model_type: "
                    + ", ".join(PART_ENUM)
                ),
            )

    # ------------------------------------------------------------------
    # EXPORTADORES
    # ------------------------------------------------------------------
    @staticmethod
    def export_obj(mesh: kernel.MeshData, path: Path) -> Path:
        """Exporta la malla a Wavefront .OBJ con normales suavizadas."""
        normals = _compute_normals(mesh)
        lines = [
            "# Wavefront OBJ - JEV CAD Engine",
            f"# Vertices: {mesh.vertex_count}  Faces: {mesh.face_count}",
            f"o {mesh.name}",
        ]
        lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in mesh.vertices.tolist())
        lines.extend(f"vn {nx:.6f} {ny:.6f} {nz:.6f}" for nx, ny, nz in normals.tolist())
        lines.extend(
            f"f {a + 1}//{a + 1} {b + 1}//{b + 1} {c + 1}//{c + 1}"
            for a, b, c in mesh.faces.tolist()
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    @staticmethod
    def export_stl(mesh: kernel.MeshData, path: Path) -> Path:
        """Exporta STL binario (impresión 3D) usando trimesh si está disponible."""
        if kernel.HAS_TRIMESH:
            path.write_bytes(mesh.to_trimesh().export(file_type="stl"))
            return path
        raise RuntimeError("STL requiere trimesh (pip install trimesh).")

    @staticmethod
    def export_glb(mesh: kernel.MeshData, path: Path, color: str = "#00f0ff") -> Path:
        """Exporta GLB binario (glTF 2.0)."""
        if kernel.HAS_TRIMESH:
            scene = kernel.trimesh.Scene()
            rgba = _hex_to_rgba(color)
            material = kernel.trimesh.visual.material.PBRMaterial(
                baseColorFactor=rgba, metallicFactor=0.85, roughnessFactor=0.3
            )
            visual = kernel.trimesh.visual.TextureVisuals(material=material)
            tm = kernel.trimesh.Trimesh(
                vertices=mesh.vertices, faces=mesh.faces, process=False, visual=visual
            )
            scene.add_geometry(tm, geom_name=mesh.name, node_name=mesh.name)
            path.write_bytes(scene.export(file_type="glb"))
            return path
        raise RuntimeError("GLB requiere trimesh (pip install trimesh).")

    @staticmethod
    def export_gltf(mesh: kernel.MeshData, path: Path, color: str = "#00f0ff") -> Path:
        """Exporta glTF 2.0 JSON con buffers embebidos en Base64 (índices uint16/uint32)."""
        positions = np.asarray(mesh.vertices, dtype=np.float32)
        normals = np.asarray(_compute_normals(mesh), dtype=np.float32)
        indices = np.asarray(mesh.faces, dtype=np.uint32).reshape(-1)

        pos_bytes = positions.tobytes(order="C")
        norm_bytes = normals.tobytes(order="C")
        use_uint32 = len(mesh.vertices) > 65535
        idx_bytes = indices.astype(np.uint32 if use_uint32 else np.uint16).tobytes(order="C")

        pad = b"\x00" * ((4 - (len(pos_bytes) + len(norm_bytes)) % 4) % 4)
        total = pos_bytes + norm_bytes + pad + idx_bytes
        uri = "data:application/octet-stream;base64," + base64.b64encode(total).decode("ascii")

        gltf = {
            "asset": {"version": "2.0", "generator": "JEV CAD Kernel"},
            "scene": 0,
            "scenes": [{"name": mesh.name + "_Scene", "nodes": [0]}],
            "nodes": [{"name": mesh.name, "mesh": 0}],
            "materials": [{
                "name": mesh.name + "_Material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": list(_hex_to_rgba(color)),
                    "metallicFactor": 0.85,
                    "roughnessFactor": 0.3,
                },
                "doubleSided": False,
            }],
            "meshes": [{
                "name": mesh.name,
                "primitives": [{
                    "attributes": {"POSITION": 0, "NORMAL": 1},
                    "indices": 2,
                    "material": 0,
                }],
            }],
            "accessors": [
                {
                    "bufferView": 0, "byteOffset": 0, "componentType": 5126,
                    "count": mesh.vertex_count, "type": "VEC3",
                    "min": positions.min(axis=0).tolist(),
                    "max": positions.max(axis=0).tolist(),
                },
                {
                    "bufferView": 1, "byteOffset": 0, "componentType": 5126,
                    "count": mesh.vertex_count, "type": "VEC3",
                },
                {
                    "bufferView": 2, "byteOffset": 0,
                    "componentType": 5125 if use_uint32 else 5123,
                    "count": int(indices.size), "type": "SCALAR",
                },
            ],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_bytes), "target": 34962},
                {"buffer": 0, "byteOffset": len(pos_bytes), "byteLength": len(norm_bytes), "target": 34962},
                {"buffer": 0, "byteOffset": len(pos_bytes) + len(norm_bytes) + len(pad),
                 "byteLength": len(idx_bytes), "target": 34963},
            ],
            "buffers": [{"byteLength": len(total), "uri": uri}],
        }
        path.write_text(json.dumps(gltf), encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # ESCENA THREE.JS
    # ------------------------------------------------------------------
    def build_viewport_scene(
        self,
        name: str,
        model_type: str,
        mesh: kernel.MeshData,
        meta: Dict[str, Any],
        color: str,
    ) -> Dict[str, Any]:
        """Construye la escena Three.js con la malla real (BufferGeometry)."""
        lo, hi = mesh.bounds
        extent = np.maximum(hi - lo, 1e-6)
        radius = float(np.linalg.norm(extent) / 2.0)
        grid_size = float(math.ceil(max(extent) * 2.4 / 5.0) * 5.0)

        positions = np.round(mesh.vertices, 4).reshape(-1).tolist()
        indices = np.asarray(mesh.faces, dtype=np.int64).reshape(-1).tolist()

        # Distancia de cámara que encuadra la esfera envolvente con el FOV del
        # Viewport (55 grados), con un 20% de aire para que la pieza no toque bordes.
        fov_rad = math.radians(55.0)
        camera_radius = (radius / math.sin(fov_rad / 2.0)) * 1.2

        return {
            "version": "2.0",
            "title": f"{name} · {model_type}",
            "background": "#050811",
            "units": "mm",
            "elements": [
                {
                    "type": "mesh",
                    "name": name,
                    "geometry": {
                        "type": "BufferGeometry",
                        "positions": positions,
                        "indices": indices,
                        "computeNormals": True,
                    },
                    "material": {
                        "type": "MeshStandardMaterial",
                        "color": color,
                        "roughness": 0.38,
                        "metalness": 0.45,
                        "flatShading": True,
                        "wireframe": False,
                    },
                    "position": [0, 0, 0],
                    "rotation": [0, 0, 0],
                    "scale": [1, 1, 1],
                }
            ],
            "camera": {
                "target": [0.0, 0.0, 0.0],
                "radius": round(max(camera_radius, 2.0), 3),
                "theta": 0.785,
                "phi": 1.05,
            },
            "grid": {"size": grid_size, "divisions": max(6, int(grid_size / 5.0))},
            "bounds": {
                "min": [round(float(v), 3) for v in lo],
                "max": [round(float(v), 3) for v in hi],
                "sphere_radius": round(radius, 3),
            },
            "meta": {
                **meta,
                "bounds_center": [round(float(v), 3) for v in mesh.center],
                "mesh_extent_mm": [round(float(v), 3) for v in extent],
            },
        }


# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------
def _compute_normals(mesh: kernel.MeshData) -> np.ndarray:
    """Normales de vértice ponderadas por área (suavizado)."""
    vertices = mesh.vertices
    faces = mesh.faces
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    face_n = np.cross(v1 - v0, v2 - v0)

    normals = np.zeros_like(vertices)
    for i in range(3):
        np.add.at(normals, faces[:, i], face_n)

    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    return normals / lengths


def _hex_to_rgba(hex_str: str) -> Tuple[float, float, float, float]:
    clean = str(hex_str or "#00f0ff").lstrip("#")
    if len(clean) == 3:
        clean = "".join(ch * 2 for ch in clean)
    if len(clean) != 6:
        clean = "00f0ff"
    try:
        r, g, b = (int(clean[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        r, g, b = (0.0, 0.94, 1.0)
    return (r, g, b, 1.0)
