"""
Suite de Pruebas Unitarias para Notificaciones por Voz Local (Piper TTS)
y Motor de Inferencia Ligera en CPU (core.notifications y core.inference).
"""
import unittest
import tempfile
import shutil
import time
from pathlib import Path

# 1. Imports de Notificaciones y Voz (Piper)
from core.notifications.events import NotificationEvent, NotificationPriority, EventType
from core.notifications.piper_tts import PiperTTS
from core.notifications.voice_notifier import VoiceNotifier
from jev.tools.voice_notification_tool import VoiceNotificationTool

# 2. Imports de Inferencia en CPU
from core.inference.cpu_engine import (
    HeuristicFastRouter,
    GGUFLocalBackend,
    BitNetBackend,
    LightweightCPUClassifier,
    ClassificationResult
)

# 3. Imports de Tools
from jev.tools import build_default_registry


class TestNotificationsAndCPUInference(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="mmae_test_voice_cpu_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # 1. PRUEBAS DE EVENTOS Y PRIORIDAD DE NOTIFICACIÓN
    # =========================================================================
    def test_notification_event_priority_ordering(self):
        """Verifica que los eventos se ordenen estrictamente por prioridad en la cola."""
        e_low = NotificationEvent.create("Detalle secundario", priority=NotificationPriority.LOW)
        e_normal = NotificationEvent.create("Progreso de tarea", priority=NotificationPriority.NORMAL)
        e_crit = NotificationEvent.create("Alerta crítica de seguridad", priority=NotificationPriority.CRITICAL)

        # En PriorityQueue, el menor valor de priority se procesa primero
        self.assertLess(e_crit, e_normal)
        self.assertLess(e_normal, e_low)
        self.assertEqual(e_crit.priority, 0)
        self.assertEqual(e_normal.priority, 2)

    # =========================================================================
    # 2. PRUEBAS DE SÍNTESIS DE VOZ PIPER (TTS)
    # =========================================================================
    def test_piper_tts_catalog_and_fallback_synthesis(self):
        """Verifica catálogo de voces y síntesis de audio WAV resiliente."""
        tts = PiperTTS(models_dir=self.temp_dir / "models", cache_dir=self.temp_dir / "cache")

        # Comprobar catálogo de idiomas
        onnx_es, json_es = tts.get_model_paths("es")
        onnx_en, json_en = tts.get_model_paths("en")
        self.assertIn("es_ES-davefx-medium.onnx", str(onnx_es))
        self.assertIn("en_US-lessac-medium.onnx", str(onnx_en))

        # Síntesis a archivo WAV (usa Piper si está el modelo o fallback nativo SAPI5/acústico)
        target_wav = self.temp_dir / "test_speech.wav"
        res_path = tts.synthesize(text="Prueba de notificación local", output_path=target_wav, language="es")
        self.assertTrue(res_path.exists())
        self.assertGreater(res_path.stat().st_size, 44)  # Tamaño de cabecera WAV válida

    # =========================================================================
    # 3. PRUEBAS DE NOTIFICADOR NO BLOQUEANTE EN SEGUNDO PLANO
    # =========================================================================
    def test_voice_notifier_non_blocking_execution(self):
        """Verifica que el notificador encole mensajes en <1ms sin congelar el hilo principal."""
        tts = PiperTTS(models_dir=self.temp_dir / "models", cache_dir=self.temp_dir / "cache")
        notifier = VoiceNotifier(tts_engine=tts, enabled=True)

        start_t = time.perf_counter()
        # Disparar múltiples avisos
        notifier.notify_task_started("Automatizar reporte en Edge")
        notifier.notify_progress("Extrayendo datos de la web")
        notifier.notify_completed("Reporte completado")
        elapsed_ms = (time.perf_counter() - start_t) * 1000.0

        # La invocación para el agente debe ser instantánea (< 50ms)
        self.assertLess(elapsed_ms, 50.0)

        # Esperar a que el worker en segundo plano procese los eventos
        for _ in range(30):
            if len(notifier.history) > 0:
                break
            time.sleep(0.1)

        notifier.shutdown(timeout=1.0)
        self.assertTrue(len(notifier.history) > 0)

    def test_voice_notification_tool_schema_and_call(self):
        """Verifica la herramienta speak_notification expuesta al LLM."""
        tts = PiperTTS(models_dir=self.temp_dir / "models", cache_dir=self.temp_dir / "cache")
        notifier = VoiceNotifier(tts_engine=tts, enabled=False)  # En modo prueba silenciado
        tool = VoiceNotificationTool(notifier=notifier)

        res = tool.execute(message="Proceso finalizado con éxito", priority="high", language="es")
        self.assertTrue(res.success)
        self.assertIn("encolada", res.output)

        schema = tool.get_openai_schema()
        self.assertEqual(schema["function"]["name"], "speak_notification")
        self.assertIn("message", schema["function"]["parameters"]["properties"])

    # =========================================================================
    # 4. PRUEBAS DE INFERENCIA LIGERA EN CPU (CPU ENGINE)
    # =========================================================================
    def test_heuristic_fast_router_latency_and_accuracy(self):
        """Verifica que el router heurístico responda en <1ms y clasifique con precisión."""
        router = HeuristicFastRouter()

        # 1. Búsqueda web
        r1 = router.classify_and_route("Busca las últimas noticias de Python en internet")
        self.assertEqual(r1.intent, "web_research")
        self.assertIn("search_web", r1.recommended_tools)
        self.assertLess(r1.latency_ms, 2.0)

        # 2. Control de aplicaciones
        r2 = router.classify_and_route("Abre la aplicación de WhatsApp para mandar un mensaje")
        self.assertEqual(r2.intent, "application_control")
        self.assertIn("open_application", r2.recommended_tools)

        # 3. Generación de código
        r3 = router.classify_and_route("Crea un script en Python para parsear este archivo CSV")
        self.assertEqual(r3.intent, "code_generation")
        self.assertIn("write_file", r3.recommended_tools)

    def test_lightweight_cpu_classifier_orchestration(self):
        """Verifica la cascada unificada del clasificador en CPU."""
        classifier = LightweightCPUClassifier()
        res = classifier.evaluate("Ejecuta un comando en PowerShell para listar archivos")
        self.assertIsInstance(res, ClassificationResult)
        self.assertIn(res.intent, ("shell_execution", "general_task"))
        self.assertTrue(res.is_safe)
        self.assertGreater(res.confidence, 0.5)

    # =========================================================================
    # 5. REGISTRO EN TOOLREGISTRY
    # =========================================================================
    def test_speak_notification_tool_registered(self):
        """Verifica que speak_notification esté registrada en el ToolRegistry central."""
        registry, _ = build_default_registry()
        tool = registry.get("speak_notification")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "speak_notification")


if __name__ == "__main__":
    unittest.main()
