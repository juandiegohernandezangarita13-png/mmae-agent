"""
Unit and integration tests for Image Generation and Multimodal Vision Recognition in JEV.
"""

import os
import unittest
import base64
from io import BytesIO
from pathlib import Path
from PIL import Image

from jev.core.image_generator import ImageGeneratorService, ImageGenerationResult
from jev.core.vision_engine import VisionEngine, VisionAnalysisResult
from jev.tools.custom.skill_image_generator import ImageGeneratorTool
from jev.tools.custom.skill_vision_recognizer import VisionRecognizerTool
from app import JarvisBridge


class TestImageGenerationAndVision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a tiny test image in memory
        cls.test_img = Image.new("RGB", (64, 64), color=(255, 100, 50))
        buf = BytesIO()
        cls.test_img.save(buf, format="PNG")
        cls.test_b64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
        cls.raw_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    def test_image_generator_service_fallback_banner(self):
        service = ImageGeneratorService()
        result = service._generate_fallback_banner("Test Prompt Cyberpunk", 256, 256, "Simulated network failure")
        self.assertIsInstance(result, ImageGenerationResult)
        self.assertTrue(result.is_success)
        self.assertTrue(Path(result.image_path).exists())
        self.assertTrue(Path(result.image_path).stat().st_size > 0)

    def test_image_generator_service_generate(self):
        service = ImageGeneratorService()
        result = service.generate("A small golden coin with neon glow", width=256, height=256)
        self.assertIsInstance(result, ImageGenerationResult)
        self.assertTrue(result.is_success)
        self.assertTrue(result.data_uri.startswith("data:image/"))
        self.assertTrue(Path(result.image_path).exists())
        self.assertIn("![", result.markdown)
        self.assertIn("]", result.markdown)

    def test_vision_engine_save_from_base64(self):
        engine = VisionEngine()
        file_path, raw = engine.save_image_from_base64(self.test_b64, prefix="unit_test")
        self.assertTrue(file_path.exists())
        self.assertEqual(raw, self.raw_b64)
        self.assertTrue(file_path.stat().st_size > 0)
        # Cleanup
        try:
            file_path.unlink()
        except Exception:
            pass

    def test_vision_engine_analyze(self):
        engine = VisionEngine()
        # Analyze our synthetic in-memory image via base64
        res = engine.analyze(self.test_b64, user_prompt="¿Qué colores tiene esta imagen?")
        self.assertIsInstance(res, VisionAnalysisResult)
        self.assertTrue(res.is_success)
        self.assertEqual(res.width, 64)
        self.assertEqual(res.height, 64)
        self.assertTrue(len(res.description) > 0)
        self.assertTrue(len(res.engine_used) > 0)

    def test_image_generator_tool(self):
        tool = ImageGeneratorTool()
        self.assertEqual(tool.name, "skill_image_generator")
        res = tool.execute(prompt="Un robot amigable estilo acuarela", width=256, height=256)
        self.assertTrue(res.success)
        self.assertIn("data_uri", res.data)
        self.assertIn("markdown", res.data)
        self.assertIn("image_path", res.data)

    def test_vision_recognizer_tool(self):
        tool = VisionRecognizerTool()
        self.assertEqual(tool.name, "skill_vision_recognizer")
        res = tool.execute(image_data=self.test_b64, prompt="Describir imagen")
        self.assertTrue(res.success)
        self.assertIn("description", res.data)
        self.assertIn("engine_used", res.data)
        self.assertIn("width", res.data)
        self.assertEqual(res.data["width"], 64)

    def test_bridge_direct_methods(self):
        bridge = JarvisBridge()
        gen_res = bridge.generate_image_direct("Paisaje minimalista")
        self.assertTrue(gen_res["success"])
        self.assertTrue(gen_res["data_uri"].startswith("data:image/"))

        vis_res = bridge.analyze_image_direct(self.test_b64, prompt="Verificar dimensiones")
        self.assertTrue(vis_res["success"])
        self.assertTrue(len(vis_res["description"]) > 0)

    def test_ui_template_contains_multimodal_elements(self):
        html_path = Path("jev/ui/templates/jarvis.html")
        self.assertTrue(html_path.exists())
        content = html_path.read_text(encoding="utf-8")

        # HTML elements
        self.assertIn('id="attachedImageBar"', content)
        self.assertIn('id="imageLightboxModal"', content)
        self.assertIn('id="btnAttach"', content)
        self.assertIn('id="fileImageInput"', content)

        # JavaScript functions
        self.assertIn('setAttachedImage', content)
        self.assertIn('clearAttachedImage', content)
        self.assertIn('handlePasteEvent', content)
        self.assertIn('openImageModal', content)
        self.assertIn('downloadImage', content)
        self.assertIn('window.onAgentImageGenerated', content)
        self.assertIn('execute_task_with_image', content)
        self.assertIn('chat-image-card', content)


if __name__ == "__main__":
    unittest.main()
