"""
Suite de Pruebas Unitarias para el Generador Programático de Vídeos de Lanzamiento (Auto-Launch Video Engine):
1. Detección y disponibilidad del binario FFmpeg en el sistema.
2. Analizador Semántico de Proyectos Web (ProjectContextParser).
3. Renderizador de Motion Graphics y Compilación de Vídeo (LaunchVideoRenderer).
4. Herramienta AutoLaunchVideoTool y acciones asociadas (check_ffmpeg, parse_project, create_launch_video).
5. Descubrimiento e invocación reflexiva en el SkillRegistry de JEV.
6. Integración reactiva en JarvisBridge._on_tool_result.
"""
import unittest
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock
from PIL import Image

from jev.tools.custom.skill_video_creator import (
    ProjectContextParser,
    LaunchVideoRenderer,
    AutoLaunchVideoTool
)
from jev.tools.base import get_auto_launch_video_tool, ToolResult
from jev.skills.manager import SkillRegistry
from jev.config import default_config
from app import JarvisBridge


class TestFFmpegAvailability(unittest.TestCase):
    """Pruebas de detección del binario local de FFmpeg."""

    def test_ffmpeg_binary_detected(self):
        """Verifica que FFmpeg se detecta correctamente en el entorno de ejecución."""
        binary = LaunchVideoRenderer.get_ffmpeg_binary()
        self.assertIsNotNone(binary, "El binario FFmpeg debe ser detectable en el sistema o PATH")
        self.assertTrue(Path(binary).exists() or shutil.which(binary) is not None)

    def test_check_ffmpeg_tool_action(self):
        """Verifica la acción 'check_ffmpeg' en AutoLaunchVideoTool."""
        tool = AutoLaunchVideoTool()
        res = tool.execute(action="check_ffmpeg")
        self.assertTrue(res.success)
        self.assertTrue(res.data.get("available"))
        self.assertIn("ffmpeg", res.output.lower())


class TestProjectContextParser(unittest.TestCase):
    """Pruebas de extracción semántica de contenido web y estructuración de guion."""

    SAMPLE_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Sistema Cuántico de Trading Autónomo</title>
  <meta name="description" content="Plataforma de alta frecuencia para análisis predictivo en mercados descentralizados.">
  <style>
    :root {
      --primary: #00ffcc;
      --secondary: #ff007f;
      background: #0a0e17;
    }
  </style>
</head>
<body>
  <h1>Trading Autónomo de Nueva Generación</h1>
  <p>Ejecución determinista de órdenes con latencia ultra-baja y modelos probabilísticos locales.</p>
  <ul>
    <li>Procesamiento en memoria a 100k ops/seg</li>
    <li>Modelos locales sin telemetría externa</li>
    <li>Visualización holográfica reactiva</li>
  </ul>
</body>
</html>"""

    def test_parse_full_html_extracts_metadata(self):
        """Verifica la extracción precisa de título, descripción, paleta y características."""
        parsed = ProjectContextParser.parse(self.SAMPLE_HTML, file_name="trading.html")

        self.assertEqual(parsed["title"], "Sistema Cuántico de Trading Autónomo")
        self.assertIn("alta frecuencia", parsed["purpose"].lower())
        self.assertGreaterEqual(len(parsed["features"]), 3)
        self.assertIn("Procesamiento en memoria a 100k ops/seg", parsed["features"])

        # Colores extraídos de CSS
        palette = parsed["palette"]
        self.assertIn(palette["primary"].lower(), ["#00ffcc", "#ff007f"])

        # Estructura del guion de 4 fases
        scenes = parsed["scenes"]
        self.assertEqual(len(scenes), 4)
        scene_types = [s["type"] for s in scenes]
        self.assertEqual(scene_types, ["hook", "demo", "features", "cta"])

        # Duración total válida
        self.assertGreater(parsed["total_duration"], 0.0)

    def test_parse_fallback_defaults(self):
        """Verifica comportamiento resiliente y valores por defecto con HTML mínimo."""
        minimal_html = "<div>Contenido simple sin tags semánticos</div>"
        parsed = ProjectContextParser.parse(minimal_html, file_name="dashboard_app.html")

        self.assertTrue(len(parsed["title"]) > 0)
        self.assertTrue(len(parsed["purpose"]) > 0)
        self.assertGreaterEqual(len(parsed["features"]), 1)
        self.assertEqual(len(parsed["scenes"]), 4)


class TestLaunchVideoRenderer(unittest.TestCase):
    """Pruebas del motor gráfico PIL y compilación acelerada con FFmpeg."""

    def setUp(self):
        self.test_dir = default_config.workspace_dir / "test_video_workspace"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.output_mp4 = self.test_dir / "test_render.mp4"

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_render_single_scene_frame(self):
        """Verifica que _render_scene_frame genera una imagen PIL con dimensiones válidas."""
        scene = {
            "type": "features",
            "badge": "FASE 03 // PRUEBA",
            "headline": "Prueba Gráfica Unitaria",
            "bullets": ["Característica Alpha", "Característica Beta"]
        }
        palette = ProjectContextParser.DEFAULT_PALETTE

        frame = LaunchVideoRenderer._render_scene_frame(
            scene=scene,
            palette=palette,
            width=1280,
            height=720,
            progress=0.5,
            scene_progress=0.4
        )

        self.assertIsInstance(frame, Image.Image)
        self.assertEqual(frame.size, (1280, 720))
        self.assertEqual(frame.mode, "RGB")

    def test_render_video_compilation(self):
        """Compila un vídeo real de corta duración y verifica la integridad del archivo MP4."""
        parsed_context = {
            "title": "JEV Demo Video",
            "purpose": "Demostración de motor de vídeo autónomo.",
            "palette": ProjectContextParser.DEFAULT_PALETTE,
            "scenes": [
                {
                    "scene_id": 1,
                    "type": "hook",
                    "badge": "DEMO 01",
                    "headline": "Inicio del Test",
                    "subtitle": "Generando fotogramas...",
                    "duration": 0.5  # 0.5 segundos para test ultrarrápido
                },
                {
                    "scene_id": 2,
                    "type": "cta",
                    "badge": "DEMO 02",
                    "headline": "Fin del Test",
                    "subtitle": "Test completado con éxito",
                    "duration": 0.5
                }
            ],
            "total_duration": 1.0
        }

        metrics = LaunchVideoRenderer.render_video(
            parsed_context=parsed_context,
            output_file=self.output_mp4,
            resolution="720p",
            fps=20
        )

        self.assertTrue(self.output_mp4.exists(), "El archivo MP4 debe haberse generado")
        self.assertGreater(metrics["file_size_bytes"], 1024, "El archivo MP4 debe tener un tamaño superior a 1KB")
        self.assertEqual(metrics["resolution"], "1280x720")
        self.assertEqual(metrics["total_frames"], 20)
        self.assertGreater(metrics["render_time_seconds"], 0.0)


class TestAutoLaunchVideoTool(unittest.TestCase):
    """Pruebas funcionales de AutoLaunchVideoTool."""

    def setUp(self):
        self.test_dir = default_config.workspace_dir / "test_tool_workspace"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.tool = AutoLaunchVideoTool(workspace_dir=self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_action_parse_project(self):
        """Verifica la acción 'parse_project' sin compilar vídeo."""
        html = "<html><head><title>Panel Analítico</title></head><body><p>Control en tiempo real</p></body></html>"
        res = self.tool.execute(action="parse_project", html_content=html)

        self.assertTrue(res.success)
        self.assertEqual(res.data["title"], "Panel Analítico")
        self.assertEqual(len(res.data["scenes"]), 4)

    def test_action_create_launch_video(self):
        """Verifica la acción 'create_launch_video' compilando el artefacto completo."""
        html = "<html><head><title>App de Lanzamiento</title></head><body><h1>Lanzamiento 2026</h1><p>Autonomía total</p></body></html>"
        res = self.tool.execute(
            action="create_launch_video",
            html_content=html,
            output_filename="promo_test.mp4",
            resolution="720p",
            fps=20
        )

        self.assertTrue(res.success, f"Error devuelto: {res.error}")
        self.assertIn("promo_test.mp4", res.output)
        self.assertIn("video_path", res.data)
        out_path = Path(res.data["video_path"])
        self.assertTrue(out_path.exists())
        self.assertGreater(out_path.stat().st_size, 1024)

    def test_factory_function(self):
        """Verifica que la función fábrica get_auto_launch_video_tool instancia la herramienta."""
        tool = get_auto_launch_video_tool()
        self.assertEqual(tool.__class__.__name__, "AutoLaunchVideoTool")
        self.assertEqual(tool.name, "skill_video_creator")


class TestSkillRegistryIntegration(unittest.TestCase):
    """Pruebas de descubrimiento y consumo a través del SkillRegistry."""

    def test_skill_video_creator_registered(self):
        """Verifica que el SkillRegistry descubre e indexa skill_video_creator como la habilidad número 20."""
        registry = SkillRegistry()
        skill = registry.get_skill("skill_video_creator")

        self.assertIsNotNone(skill, "skill_video_creator debe ser descubierta por SkillRegistry")
        self.assertEqual(skill.metadata.name, "skill_video_creator")
        self.assertEqual(skill.metadata.category, "multimedia_video")
        self.assertIn("video de lanzamiento", skill.metadata.trigger_keywords)
        self.assertIn("ffmpeg", skill.metadata.dependencies)

    def test_skill_execution_via_registry(self):
        """Verifica la invocación reflexiva mediante SkillRegistry.execute_skill()."""
        registry = SkillRegistry()
        res = registry.execute_skill(
            "skill_video_creator",
            action="parse_project",
            html_content="<title>Registro Modular</title><h1>Capacidad Verificada</h1>"
        )

        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res["data"]["title"], "Registro Modular")


class TestJarvisBridgeVideoNotification(unittest.TestCase):
    """Pruebas de notificación y reactividad en JarvisBridge."""

    def test_on_tool_result_notifies_video_compilation(self):
        """Verifica que al finalizar la compilación de vídeo se despacha una notificación en el stream de pensamientos."""
        from jev.config import AgentConfig
        cfg = AgentConfig()
        bridge = JarvisBridge(cfg)
        bridge._on_thought = MagicMock()
        bridge._eval_js = MagicMock()

        result = ToolResult(
            success=True,
            output="Vídeo compilado con éxito",
            data={
                "video_path": "c:/workspace/launch_video.mp4",
                "title": "Sistema Cuántico"
            }
        )

        bridge._on_tool_result("skill_video_creator", result)

        # Verificar que se invocó _on_thought con la notificación del vídeo
        bridge._on_thought.assert_called()
        call_args = [str(arg) for call in bridge._on_thought.call_args_list for arg in call[0]]
        self.assertTrue(any("Vídeo de Lanzamiento Compilado" in a for a in call_args))


if __name__ == "__main__":
    unittest.main()
