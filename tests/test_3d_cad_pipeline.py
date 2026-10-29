"""
Pruebas de la tubería de diseño 3D / CAD de JEV.

Cubren los cuatro puntos que impedían generar un diseño 3D funcional:
1. Enrutamiento MoAE: las herramientas 3D deben estar expuestas al modelo.
2. Esquema de skills: los parámetros con valor por defecto no son obligatorios.
3. Kernel CAD: geometría real, estanca, con booleanas y exportaciones válidas.
4. Puente UI: la escena generada se despacha al Viewport Three.js.
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jev.core import cad_kernel as kernel
from jev.core.mythos_engine import MoAERouter
from jev.skills.manager import Skill, SkillMetadata, SkillRegistry, SkillToolAdapter
from jev.skills.manager import SkillRegistry
from jev.tools import build_default_registry
from jev.tools.base import ToolRegistry, ToolResult
from jev.tools.custom.skill_cad_mesh import ParametricCadMeshTool
from jev.tools.viewport import ExecuteViewportScriptTool, Render3DSceneTool


def _registry() -> ToolRegistry:
    """Registro completo: replica las condiciones reales del agente."""
    registry, _ = build_default_registry()
    for adapter in SkillRegistry().to_tool_adapters():
        if not registry.get(adapter.name):
            registry.register(adapter)
    return registry


class TestMoAERouting3D(unittest.TestCase):
    """El router debe habilitar el cluster de diseño 3D (causa raíz del fallo)."""

    def setUp(self) -> None:
        self.router = MoAERouter()
        self.tools = _registry().to_openai_tools()

    def _enabled(self, goal: str):
        tools, experts = self.router.route_tools(goal, self.tools)
        return {t["function"]["name"] for t in tools}, experts

    def test_spanish_3d_requests_enable_cad_tools(self):
        prompts = [
            "genera un diseño 3D de un engranaje de 24 dientes",
            "disena una brida con 6 tornillos",
            "crea un modelo 3d de una carcasa para Arduino",
            "necesito el diseño en 3D de una polea",
            "hazme un modelo 3d gltf de un resorte",
        ]
        for prompt in prompts:
            enabled, experts = self._enabled(prompt)
            with self.subTest(prompt=prompt):
                self.assertIn("skill_cad_mesh", enabled)
                self.assertIn("render_3d_scene", enabled)
                self.assertTrue(any("3D" in name for name in experts))

    def test_non_3d_request_does_not_enable_cad(self):
        enabled, experts = self._enabled("genera una imagen de un gato")
        self.assertNotIn("skill_cad_mesh", enabled)
        self.assertNotIn("3D CAD Design & Parametric Modeling", experts)

    def test_explicit_tool_name_forces_enable(self):
        enabled, _ = self._enabled("usa skill_cad_mesh para la pieza")
        self.assertIn("skill_cad_mesh", enabled)


class TestSkillAdapterSchema(unittest.TestCase):
    """Los parámetros con default no deben exigirse en la llamada."""

    def test_only_params_without_default_are_required(self):
        metadata = SkillMetadata(
            name="skill_demo",
            description="demo",
            parameters={
                "shape": {"type": "string", "description": "forma"},
                "params": {"type": "object", "description": "opciones", "default": {}},
                "color": {"type": "string", "description": "color", "default": "#fff"},
            },
        )
        adapter = SkillToolAdapter(Skill(Path("."), metadata, lambda **kw: {"ok": True}))
        self.assertEqual(adapter.parameters["required"], ["shape"])

    def test_registry_accepts_call_with_only_required_param(self):
        metadata = SkillMetadata(
            name="skill_demo2",
            description="demo",
            parameters={
                "shape": {"type": "string", "description": "forma"},
                "params": {"type": "object", "description": "opciones", "default": {}},
            },
        )
        adapter = SkillToolAdapter(
            Skill(Path("."), metadata, lambda shape="box", params=None: {"status": "success", "shape": shape})
        )
        registry = ToolRegistry()
        registry.register(adapter)
        result = registry.execute_call("skill_demo2", {"shape": "torus"})
        self.assertTrue(result.success, msg=result.error)

    def test_all_bundled_skills_have_usable_schemas(self):
        registry = SkillRegistry()
        for skill in registry.to_tool_adapters():
            for name, spec in skill.parameters.get("properties", {}).items():
                with self.subTest(skill=skill.name, param=name):
                    self.assertIsInstance(spec, dict)
                    self.assertIn("type", spec)


class TestCadKernel(unittest.TestCase):
    """Todas las piezas deben ser sólidos reales, estancos y con volumen."""

    def test_every_part_builds_watertight(self):
        for model_type in kernel.list_part_types():
            with self.subTest(part=model_type):
                mesh, meta = kernel.build_part(model_type)
                self.assertGreater(mesh.vertex_count, 7)
                self.assertGreater(mesh.face_count, 11)
                self.assertGreater(meta["volume_mm3"], 0.0)
                self.assertTrue(meta["watertight"], msg=f"{model_type} no es estanco")

    def test_gear_has_real_teeth_and_bore(self):
        mesh, meta = kernel.build_part(
            "spur_gear",
            {"teeth": 20, "pitch_radius": 12, "thickness": 4, "bore_radius": 3},
        )
        radii = (mesh.vertices[:, :2] ** 2).sum(axis=1) ** 0.5
        self.assertAlmostEqual(float(radii.min()), 3.0, delta=0.05)  # agujero real
        self.assertGreater(float(radii.max()), 12.0)  # cresta del diente
        self.assertTrue(meta["watertight"])

    def test_gear_profile_is_simple_and_monotonic(self):
        """Regresión: el perfil no debe auto-intersectarse (dientes 'en cuchilla')."""
        for teeth in (12, 18, 26, 40):
            with self.subTest(teeth=teeth):
                contour = kernel.gear_contour(teeth, 20.0, 3.0)
                angles = np.unwrap(np.arctan2(contour[:, 1], contour[:, 0]))
                deltas = np.diff(angles)
                self.assertTrue((deltas > -1e-9).all(), "el ángulo del perfil retrocede")
                radii = np.linalg.norm(contour, axis=1)
                self.assertAlmostEqual(float(radii.min()), 18.5, delta=0.05)
                self.assertAlmostEqual(float(radii.max()), 21.5, delta=0.05)

    def test_flange_bolt_holes_remove_material(self):
        without_holes, _ = kernel.build_part(
            "flange", {"outer_radius": 30, "inner_radius": 12, "thickness": 6, "bolt_count": 0}
        )
        with_holes, _ = kernel.build_part(
            "flange", {"outer_radius": 30, "inner_radius": 12, "thickness": 6, "bolt_count": 6}
        )
        self.assertLess(with_holes.volume(), without_holes.volume() * 0.98)

    def test_booleans_actually_need_manifold(self):
        # documenta la dependencia y evita regresiones silenciosas
        self.assertTrue(kernel.HAS_MANIFOLD, "manifold3d debe estar instalado")
        self.assertTrue(kernel.HAS_TRIMESH, "trimesh debe estar instalado")


class TestCadToolExports(unittest.TestCase):
    """La herramienta debe exportar formatos válidos y una escena con malla real."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp())
        cls.tool = ParametricCadMeshTool(workspace_dir=cls.tmp)
        cls.result = cls.tool.execute(
            model_type="flange",
            name="Test_Flange",
            parameters={"outer_radius": 25, "inner_radius": 10, "thickness": 5, "bolt_count": 6},
            color="#00f0ff",
        )

    def test_execution_succeeds(self):
        self.assertTrue(self.result.success, msg=self.result.error)
        self.assertTrue(self.result.data["watertight"])
        self.assertGreater(self.result.data["vertex_count"], 100)

    def test_all_formats_written(self):
        files = self.result.data["files"]
        for fmt in ("obj", "stl", "glb", "gltf", "scene"):
            with self.subTest(fmt=fmt):
                self.assertIn(fmt, files)
                self.assertTrue(Path(files[fmt]).exists())
                self.assertGreater(Path(files[fmt]).stat().st_size, 0)

    def test_scene_contains_real_buffer_geometry(self):
        scene = self.result.data["scene"]
        self.assertEqual(len(scene["elements"]), 1)
        element = scene["elements"][0]
        self.assertEqual(element["geometry"]["type"], "BufferGeometry")
        positions = element["geometry"]["positions"]
        indices = element["geometry"]["indices"]
        self.assertEqual(len(positions), self.result.data["vertex_count"] * 3)
        self.assertEqual(len(indices), self.result.data["face_count"] * 3)
        self.assertEqual(len(indices) % 3, 0)
        self.assertGreater(scene["camera"]["radius"], 0)

    def test_written_scene_file_matches_payload(self):
        scene_path = Path(self.result.data["files"]["scene"])
        on_disk = json.loads(scene_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["elements"][0]["name"], "Test_Flange")

    def test_exported_meshes_reload(self):
        import trimesh

        stl = trimesh.load(self.result.data["files"]["stl"])
        self.assertGreater(len(stl.faces), 100)
        glb = trimesh.load(self.result.data["files"]["glb"])
        geometries = list(glb.geometry.values()) if hasattr(glb, "geometry") else [glb]
        self.assertGreater(len(geometries[0].faces), 100)

    def test_gltf_is_valid_json_and_uses_correct_index_type(self):
        gltf = json.loads(Path(self.result.data["files"]["gltf"]).read_text(encoding="utf-8"))
        self.assertEqual(gltf["asset"]["version"], "2.0")
        self.assertEqual(len(gltf["bufferViews"]), 3)
        component = gltf["accessors"][2]["componentType"]
        expected = 5125 if self.result.data["vertex_count"] > 65535 else 5123
        self.assertEqual(component, expected)

    def test_unknown_part_returns_actionable_error(self):
        res = self.tool.execute(model_type="nave_espacial")
        self.assertFalse(res.success)
        self.assertIn("spur_gear", res.error)


class TestViewportTools(unittest.TestCase):
    """Escenas declarativas y scripts nativos pasan por el canal correcto."""

    def test_render_scene_accepts_buffer_geometry(self):
        tool = Render3DSceneTool()
        scene = {
            "elements": [{
                "type": "mesh",
                "name": "Tri",
                "geometry": {
                    "type": "BufferGeometry",
                    "positions": [0, 0, 0, 1, 0, 0, 0, 1, 0],
                    "indices": [0, 1, 2],
                },
                "material": {"color": "#00f0ff"},
            }]
        }
        res = tool.execute(scene=scene)
        self.assertTrue(res.success, msg=res.error)
        self.assertIn("scene", res.data)
        self.assertEqual(res.data["mesh_count"], 1)

    def test_render_scene_rejects_unknown_geometry(self):
        res = Render3DSceneTool().execute(
            scene={"elements": [{"type": "mesh", "geometry": {"type": "NopeGeometry"}}]}
        )
        self.assertFalse(res.success)
        self.assertIn("no soportada", res.error)

    def test_render_scene_rejects_empty_scene(self):
        res = Render3DSceneTool().execute(scene={"elements": []})
        self.assertFalse(res.success)

    def test_viewport_script_rejects_duplicate_renderer(self):
        tool = ExecuteViewportScriptTool()
        self.assertFalse(tool.execute(js_code="new THREE.WebGLRenderer()").success)
        res = tool.execute(js_code="dynamicGroup.rotation.y += 0.01;")
        self.assertTrue(res.success)
        self.assertIn("js_code", res.data)


class TestBridgeDispatch(unittest.TestCase):
    """El puente PyWebView debe despachar la escena y los scripts al frontend."""

    def _bridge(self):
        from app import JarvisBridge

        bridge = object.__new__(JarvisBridge)
        calls = []
        bridge._eval_js = lambda js: calls.append(js)
        bridge._on_thought = lambda text: calls.append("THOUGHT:" + text)
        bridge.execute_viewport_script = lambda js: calls.append("SCRIPT:" + js)
        return bridge, calls

    def test_cad_result_is_sent_to_viewport(self):
        bridge, calls = self._bridge()
        scene = {"elements": [{"type": "mesh", "geometry": {"type": "BoxGeometry"}}]}
        result = ToolResult(
            success=True,
            output="ok",
            data={"scene": scene, "name": "Pieza", "vertex_count": 8, "face_count": 12, "engine": "manifold3d"},
        )
        bridge._on_tool_result("skill_cad_mesh", result)
        joined = "\n".join(calls)
        self.assertIn("window.onRender3DScene", joined)
        self.assertIn("Pieza", joined)

    def test_viewport_script_result_is_executed(self):
        bridge, calls = self._bridge()
        result = ToolResult(success=True, output="ok", data={"js_code": "dynamicGroup.rotation.y += 0.01;"})
        bridge._on_tool_result("execute_viewport_script", result)
        self.assertTrue(any(c.startswith("SCRIPT:") for c in calls))


if __name__ == "__main__":
    unittest.main()
