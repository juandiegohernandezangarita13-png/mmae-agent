"""
Suite de Pruebas Unitarias para Aislamiento de Runtime (Frontend vs Backend)
y Verificación Estricta de APIs Three.js en JEV v2.5.
"""
import unittest
import json
from unittest.mock import MagicMock
from jev.core.post_reflection import PostExecutionAuditEngine
from jev.skills.skill_mesh_generator.handler import handle as handle_mesh
from app import JarvisBridge


class TestRuntimeIsolationAndApiCheck(unittest.TestCase):
    def setUp(self):
        self.mock_llm = MagicMock()
        self.auditor = PostExecutionAuditEngine(self.mock_llm)

    def test_language_bleeding_detection(self):
        """Verifica que bloques marcados como Python con sintaxis nativa de JS sean interceptados."""
        bad_code = (
            "```python\n"
            "const scene = new THREE.Scene();\n"
            "let mesh = new THREE.Mesh();\n"
            "window.dynamicGroup.add(mesh);\n"
            "```"
        )
        report = self.auditor.audit_and_critique("Generar script 3D", bad_code)
        self.assertFalse(report.passed)
        self.assertTrue(any("Language Bleeding" in iss for iss in report.issues))
        # Verificar autocorrección determinista de tag python a javascript
        self.assertIsNotNone(report.corrected_answer)
        self.assertIn("```javascript", report.corrected_answer)

    def test_metaprogramming_re_sub_detection(self):
        """Verifica que scripts de Python manipulando código frontend con re.sub sean detectados."""
        bad_meta = (
            "```python\n"
            "import re\n"
            "scene_script = 'const x = 1;'\n"
            "modified = re.sub(r'1', '2', scene_script)\n"
            "print(modified)\n"
            "```"
        )
        report = self.auditor.audit_and_critique("Inyectar código en viewport", bad_meta)
        self.assertFalse(report.passed)
        self.assertTrue(any("Sobreingeniería innecesaria" in iss for iss in report.issues))

    def test_threejs_arrow_geometry_hallucination_detection(self):
        """Verifica que THREE.ArrowGeometry sea detectado como alucinación y autocorregido."""
        bad_three = (
            "```javascript\n"
            "const geo = new THREE.ArrowGeometry(1, 2);\n"
            "const mat = new THREE.MeshBasicMaterial({ color: 0x00f0ff });\n"
            "const arrow = new THREE.Mesh(geo, mat);\n"
            "dynamicGroup.add(arrow);\n"
            "```"
        )
        report = self.auditor.audit_and_critique("Crear flecha 3D", bad_three)
        self.assertFalse(report.passed)
        self.assertTrue(any("Alucinación de API Three.js" in iss for iss in report.issues))
        # Autocorrección determinista
        self.assertIsNotNone(report.corrected_answer)
        self.assertIn("THREE.ArrowHelper", report.corrected_answer)
        self.assertNotIn("THREE.ArrowGeometry", report.corrected_answer)

    def test_duplicate_renderer_detection(self):
        """Verifica que instanciar new THREE.WebGLRenderer en un script de escena sea penalizado."""
        duplicate_renderer_code = (
            "```javascript\n"
            "const renderer = new THREE.WebGLRenderer();\n"
            "const camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);\n"
            "const scene = new THREE.Scene();\n"
            "```"
        )
        report = self.auditor.audit_and_critique("Configurar escena 3D", duplicate_renderer_code)
        self.assertFalse(report.passed)
        self.assertTrue(any("Duplicación de runtime (No Duplicate Renderers)" in iss for iss in report.issues))

    def test_valid_threejs_script_approved(self):
        """Verifica que un script JavaScript nativo inyectado sobre dynamicGroup sea aprobado."""
        valid_js = (
            "```javascript\n"
            "const dir = new THREE.Vector3(0, 1, 0).normalize();\n"
            "const origin = new THREE.Vector3(0, 0, 0);\n"
            "const arrow = new THREE.ArrowHelper(dir, origin, 3, 0x00f0ff);\n"
            "dynamicGroup.add(arrow);\n"
            "```"
        )
        report = self.auditor.audit_and_critique("Añadir flecha al viewport", valid_js)
        self.assertTrue(report.passed)
        self.assertEqual(len(report.issues), 0)

    def test_mesh_generator_arrow_helper(self):
        """Verifica que la habilidad skill_mesh_generator soporte 'arrow' y 'arrow_helper'."""
        res = handle_mesh(shape="arrow", params={"length": 5.0, "color": "#00f0ff"})
        self.assertEqual(res["status"], "success")
        elem = res["element"]
        self.assertEqual(elem["type"], "arrow_helper")
        self.assertEqual(elem["length"], 5.0)
        self.assertEqual(elem["color"], "#00f0ff")

        # Con alias arrow_helper
        res2 = handle_mesh(shape="arrow_helper", params={"headWidth": 0.8})
        self.assertEqual(res2["element"]["type"], "arrow_helper")
        self.assertEqual(res2["element"]["headWidth"], 0.8)

    def test_jarvis_bridge_execute_viewport_script(self):
        """Verifica que JarvisBridge exponga execute_viewport_script sin errores."""
        bridge = JarvisBridge.__new__(JarvisBridge)
        bridge._window = MagicMock()

        bridge.execute_viewport_script("dynamicGroup.rotation.y += 0.5;")
        bridge._window.evaluate_js.assert_called_once()
        called_arg = bridge._window.evaluate_js.call_args[0][0]
        self.assertIn("window.executeViewportScript", called_arg)


if __name__ == "__main__":
    unittest.main()
