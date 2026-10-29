"""
Herramientas de control del Viewport 3D de JEV.

Permiten al agente de diseño proyectar escenas 3D declarativas (JSON Three.js)
o inyectar scripts JavaScript nativos sobre la escena activa, sin generar
código Python que contenga JavaScript. El puente PyWebView (JarvisBridge) se
encarga de despachar el payload al frontend.
"""
from typing import Any, Dict, List, Optional
import json

from jev.tools.base import BaseTool, ToolResult


#: Geometrías disponibles en la versión de Three.js empaquetada (r128).
GEOMETRY_TYPES = {
    "BufferGeometry", "BoxGeometry", "SphereGeometry", "CylinderGeometry",
    "ConeGeometry", "TorusGeometry", "PlaneGeometry", "CircleGeometry",
    "RingGeometry", "LatheGeometry",
}


class Render3DSceneTool(BaseTool):
    """Proyecta una escena 3D declarativa en el Viewport Three.js en vivo."""

    name = "render_3d_scene"
    description = (
        "Renderiza una escena 3D declarativa en el Viewport holográfico en vivo. "
        "Usa geometrías nativas de Three.js (BoxGeometry, SphereGeometry, CylinderGeometry, "
        "TorusGeometry, PlaneGeometry) o mallas reales con BufferGeometry (positions + indices). "
        "Es la vía correcta para diseñar escenas 3D sin escribir JavaScript dentro de Python."
    )
    parameters = {
        "type": "object",
        "properties": {
            "scene": {
                "type": "object",
                "description": (
                    "Escena en formato Three.js JSON: {'background': '#050811', 'elements': ["
                    "{'type':'mesh','name':'Pieza','geometry':{'type':'BoxGeometry','parameters':{'width':2,'height':2,'depth':2}},"
                    "'material':{'color':'#00f0ff','metalness':0.8,'roughness':0.25},'position':[0,0,0]}, ...], "
                    "'camera':{'radius':12,'theta':0.785,'phi':1.05}}"
                )
            },
            "title": {
                "type": "string",
                "description": "Título corto mostrado en el HUD del Viewport.",
                "default": "Escena 3D"
            }
        },
        "required": ["scene"]
    }

    def execute(self, scene: Any = None, title: str = "Escena 3D", **kwargs: Any) -> ToolResult:
        if scene is None:
            return ToolResult(success=False, output="", error="Falta el parámetro 'scene'.")
        try:
            data = json.loads(scene) if isinstance(scene, str) else scene
        except json.JSONDecodeError as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"La escena no es un JSON válido: {exc}. Envía un objeto, no código JavaScript.",
            )
        if not isinstance(data, dict):
            return ToolResult(success=False, output="", error="La escena debe ser un objeto JSON.")

        elements = data.get("elements")
        if elements is None:
            elements = data.get("meshes")
        if not isinstance(elements, list) or not elements:
            return ToolResult(
                success=False,
                output="",
                error=(
                    "La escena debe incluir una lista 'elements' no vacía con al menos una malla. "
                    "Ejemplo: {'elements': [{'type': 'mesh', 'geometry': {'type': 'BoxGeometry', "
                    "'parameters': {'width': 2, 'height': 2, 'depth': 2}}, 'material': {'color': '#00f0ff'}}]}"
                ),
            )

        cleaned: List[Dict[str, Any]] = []
        for index, item in enumerate(elements):
            if not isinstance(item, dict):
                return ToolResult(success=False, output="", error=f"El elemento {index} no es un objeto JSON.")
            kind = str(item.get("type", "mesh")).lower()
            if kind == "mesh":
                geometry = item.get("geometry") or {}
                g_type = str(geometry.get("type", "BoxGeometry"))
                if g_type not in GEOMETRY_TYPES:
                    return ToolResult(
                        success=False,
                        output="",
                        error=(
                            f"Geometría no soportada '{g_type}'. Usa una de: "
                            + ", ".join(sorted(GEOMETRY_TYPES))
                        ),
                    )
                if g_type == "BufferGeometry":
                    positions = geometry.get("positions")
                    indices = geometry.get("indices")
                    if not positions or not indices:
                        return ToolResult(
                            success=False,
                            output="",
                            error=(
                                "BufferGeometry requiere 'positions' (lista plana [x,y,z,...]) "
                                "e 'indices' (lista plana de triángulos)."
                            ),
                        )
            elif kind in ("arrow", "arrow_helper", "grid_helper"):
                pass
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Tipo de elemento no soportado: '{kind}'. Usa 'mesh', 'arrow_helper' o 'grid_helper'.",
                )
            cleaned.append(item)

        scene_dict = dict(data)
        scene_dict["elements"] = cleaned
        if title:
            scene_dict.setdefault("title", title)

        mesh_count = sum(1 for item in cleaned if str(item.get("type", "mesh")).lower() == "mesh")
        return ToolResult(
            success=True,
            output=(
                f"Escena 3D proyectada en el Viewport: {mesh_count} malla(s), "
                f"{len(cleaned)} elemento(s). Fondo '{scene_dict.get('background', '#050811')}'."
            ),
            data={"scene": scene_dict, "title": title, "mesh_count": mesh_count},
        )


class ExecuteViewportScriptTool(BaseTool):
    """Inyecta JavaScript nativo en la escena Three.js activa del Viewport."""

    name = "execute_viewport_script"
    description = (
        "Ejecuta JavaScript nativo sobre la escena Three.js ya montada (window.scene, "
        "window.camera, window.renderer, window.dynamicGroup, window.controls). "
        "Útil para animaciones, luces o transformaciones avanzadas. "
        "PROHIBIDO crear un nuevo WebGLRenderer, PerspectiveCamera o Scene."
    )
    parameters = {
        "type": "object",
        "properties": {
            "js_code": {
                "type": "string",
                "description": (
                    "Código JavaScript puro que se ejecuta en el navegador. Tiene disponibles las variables "
                    "scene, camera, renderer, dynamicGroup y THREE. Ejemplo: "
                    "'const g = new THREE.ConeGeometry(1.5, 3, 32); dynamicGroup.add(new THREE.Mesh(g, new THREE.MeshStandardMaterial({color: 0xff0077})));'"
                )
            }
        },
        "required": ["js_code"]
    }

    def execute(self, js_code: str = "", **kwargs: Any) -> ToolResult:
        code = (js_code or "").strip()
        if not code:
            return ToolResult(success=False, output="", error="Falta el parámetro 'js_code'.")
        forbidden = ["new THREE.WebGLRenderer", "new THREE.Scene", "new THREE.PerspectiveCamera"]
        hits = [frag for frag in forbidden if frag in code]
        if hits:
            return ToolResult(
                success=False,
                output="",
                error=(
                    "El script intenta duplicar la infraestructura del Viewport ("
                    + ", ".join(hits)
                    + "). Usa la escena y la cámara activas: scene, camera, renderer y dynamicGroup."
                ),
            )
        return ToolResult(
            success=True,
            output="Script JavaScript encolado para su ejecución sobre la escena activa del Viewport.",
            data={"js_code": code, "viewport_script": code},
        )
