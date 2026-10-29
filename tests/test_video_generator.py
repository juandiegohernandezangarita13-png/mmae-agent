"""
Pruebas unitarias para la herramienta de generación de video HyperFrames (HeyGen):
- Verificación del entorno de renderizado
- Renderizado de composiciones HTML5/CSS/GSAP a MP4 determinista
- Enrutamiento temático MoAE para producción audiovisual
- Protocolo de verificación empírica en ActionVerifier
"""
import unittest
import tempfile
import shutil
from pathlib import Path

from jev.tools.video_generator import HyperFramesVideoTool
from jev.core.mythos_engine import MoAERouter
from jev.tools import build_default_registry
from jev.core.verifier import ActionVerifier


class TestHyperFramesVideoGenerator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.tool = HyperFramesVideoTool(workspace_dir=self.temp_dir)
        self.verifier = ActionVerifier(workspace_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_environment(self):
        res = self.tool.execute(action="check_environment")
        self.assertTrue(res.success, f"Error en check_environment: {res.error}")
        self.assertIn("Diagnóstico de HyperFrames", res.output)

    def test_moae_router_activates_video_cluster(self):
        router = MoAERouter()
        registry, _ = build_default_registry()
        all_tools = registry.to_openai_tools()

        tools, active_clusters = router.route_tools(
            "necesito renderizar un video animado en mp4 para youtube shorts",
            all_tools
        )
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("render_hyperframes_video", tool_names)
        self.assertTrue(any("HyperFrames" in c for c in active_clusters))

    def test_render_html_composition_to_mp4(self):
        # Renderizado de prueba de 2 segundos en resolución vertical (TikTok / Reels)
        html_sample = """<!doctype html>
<html>
<head>
  <meta charset="UTF-8" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    body { width: 1080px; height: 1920px; background: #000; color: #fff; display: flex; align-items: center; justify-content: center; font-family: sans-serif; }
    h1 { font-size: 80px; color: #00f0ff; }
  </style>
</head>
<body>
  <div data-composition-id="main" data-start="0" data-duration="2" data-width="1080" data-height="1920">
    <h1 id="title">JEV CORE</h1>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.fromTo("#title", { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1, duration: 1 });
    window.__timelines = window.__timelines || {};
    window.__timelines["main"] = tl;
    tl.seek(0);
  </script>
</body>
</html>"""
        res = self.tool.execute(
            action="render_html",
            project_name="unit_test_reel",
            html_content=html_sample,
            duration_seconds=2,
            resolution="portrait",
            output_filename="reel_test.mp4"
        )
        self.assertTrue(res.success, f"Error en render_html: {res.error}")
        self.assertIn("Video Renderizado Exitosamente", res.output)
        self.assertIsNotNone(res.data)
        self.assertIn("video_path", res.data)

        # Verificar archivo físico en disco
        v_path = Path(res.data["video_path"])
        self.assertTrue(v_path.exists())
        self.assertGreater(v_path.stat().st_size, 0)

        # Validar con ActionVerifier (Reflection loop)
        v_res = self.verifier.verify_action("render_hyperframes_video", {"action": "render_html"}, res)
        self.assertTrue(v_res.passed, f"ActionVerifier rechazó el video: {v_res.reason}")


if __name__ == "__main__":
    unittest.main()
