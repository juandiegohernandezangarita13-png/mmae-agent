"""
Suite de Pruebas Unitarias para el Subsistema de Voz y Audio Local (Voice Studio Engine):
1. Síntesis acústica local y clonación zero-shot (VoiceEngineTool).
2. Transcripción STT local y pipeline de doblaje audio-a-audio.
3. Gestión de perfiles tímbricos en data/voice_samples/.
4. Integración con JarvisBridge (toggle_voice_synthesis, síntesis en hilo daemon).
5. Descubrimiento y ejecución en SkillRegistry y DynamicToolManager.
"""
import unittest
import json
import time
import wave
import shutil
from pathlib import Path

from jev.tools.custom.skill_voice_engine import VoiceEngineTool
from app import JarvisBridge
from jev.skills.manager import SkillRegistry
from jev.tools.base import ToolRegistry
from jev.tools.dynamic_loader import DynamicToolManager
from jev.config import default_config


class TestVoiceEngineTool(unittest.TestCase):
    """Pruebas funcionales de síntesis, clonación y transcripción local."""

    def setUp(self):
        self.tool = VoiceEngineTool()
        self.test_audio_dir = Path("data/cache/test_voice_tmp")
        self.test_audio_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_audio_dir.exists():
            shutil.rmtree(self.test_audio_dir, ignore_errors=True)

    def test_synthesize_speech_creates_valid_wav(self):
        """Verifica que la síntesis genere un archivo WAV PCM válido con estructura de cabecera correcta."""
        out_name = "test_synth.wav"
        res = self.tool.execute(
            action="synthesize_speech",
            text="JEV sistema autónomo inicializado con éxito.",
            language="es",
            output_filename=out_name
        )
        self.assertTrue(res.success, res.error)
        audio_path = Path(res.data["audio_path"])
        self.assertTrue(audio_path.exists())
        self.assertGreater(audio_path.stat().st_size, 1000)

        # Validar formato WAV PCM
        with wave.open(str(audio_path), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)  # 16-bit
            self.assertEqual(wf.getframerate(), 22050)
            self.assertGreater(wf.getnframes(), 0)

    def test_voice_cloning_with_reference_sample(self):
        """Verifica la clonación tímbrica utilizando una muestra de referencia del usuario."""
        # Registrar primero una muestra
        reg_res = self.tool.execute(
            action="register_voice_profile",
            speaker_name="test_user_sample"
        )
        self.assertTrue(reg_res.success)
        ref_path = reg_res.data["saved_path"]
        self.assertTrue(Path(ref_path).exists())

        # Clonar usando esa muestra
        clone_res = self.tool.execute(
            action="clone_voice",
            text="Confirmación de identidad vocal procesada en el entorno local.",
            speaker_wav=ref_path,
            language="es",
            output_filename="cloned_test.wav"
        )
        self.assertTrue(clone_res.success)
        cloned_file = Path(clone_res.data["audio_path"])
        self.assertTrue(cloned_file.exists())
        self.assertGreater(cloned_file.stat().st_size, 1000)

    def test_transcription_and_audio_to_audio_pipeline(self):
        """Verifica el pipeline completo de doblaje: STT -> traducción -> TTS."""
        # Sintetizar audio de prueba
        sample_file = self.tool.cache_dir / "sample_speech.wav"
        self.tool._generate_local_acoustic_wav("hola bienvenido tarea sistema", sample_file)

        # Ejecutar pipeline de doblaje audio-a-audio
        dub_res = self.tool.execute(
            action="audio_to_audio_translate",
            audio_path=str(sample_file),
            language="es",
            target_language="en",
            output_filename="dubbed_en.wav"
        )
        self.assertTrue(dub_res.success)
        self.assertIn("original_text", dub_res.data)
        self.assertIn("translated_text", dub_res.data)
        self.assertTrue(Path(dub_res.data["output_audio"]).exists())


class TestJarvisBridgeVoiceIntegration(unittest.TestCase):
    """Pruebas de la integración del motor de voz con JarvisBridge."""

    def test_toggle_voice_synthesis(self):
        """Verifica que toggle_voice_synthesis active y desactive el estado interno."""
        bridge = JarvisBridge.__new__(JarvisBridge)
        bridge._voice_enabled = False

        bridge.toggle_voice_synthesis(True)
        self.assertTrue(bridge._voice_enabled)

        bridge.toggle_voice_synthesis(False)
        self.assertFalse(bridge._voice_enabled)

    def test_async_voice_synthesis_dispatches_event(self):
        """Verifica que _synthesize_voice_async despache window.playAudioOutput a la UI en hilo daemon."""
        bridge = JarvisBridge.__new__(JarvisBridge)
        bridge._voice_enabled = True
        bridge._voice_tool = VoiceEngineTool()

        evaluated_scripts = []
        bridge._eval_js = lambda js: evaluated_scripts.append(js)

        # Despachar síntesis
        bridge._synthesize_voice_async("Operación de voz completada.")

        # Esperar brevemente a que el hilo daemon complete la generación
        for _ in range(20):
            if any("window.playAudioOutput" in js for js in evaluated_scripts):
                break
            time.sleep(0.05)

        self.assertTrue(
            any("window.playAudioOutput" in js for js in evaluated_scripts),
            "JarvisBridge debe emitir window.playAudioOutput a la interfaz."
        )


class TestVoiceEngineRegistry(unittest.TestCase):
    """Verifica que skill_voice_engine esté disponible en SkillRegistry y ToolRegistry."""

    def test_skill_registered_in_skill_registry(self):
        registry = SkillRegistry()
        skill = registry.get_skill("skill_voice_engine")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.metadata.name, "skill_voice_engine")

        # Ejecución pasiva
        res = registry.execute_skill("skill_voice_engine", action="synthesize_speech", text="Test en registro.")
        self.assertEqual(res.get("status"), "success")

    def test_loaded_by_dynamic_tool_manager(self):
        tool_reg = ToolRegistry()
        dyn_mgr = DynamicToolManager(tool_reg)
        loaded = dyn_mgr.load_all()
        self.assertIn("skill_voice_engine", loaded)


if __name__ == "__main__":
    unittest.main()
