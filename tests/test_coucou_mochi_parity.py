"""
Pruebas de paridad visual y funcional de la Isla flotante Mochi / Coucou en JEV.
Verifica:
  1. API de chat y envío de tareas desde la isla flotante (send_chat, send_file_drop, get_chat_history).
  2. Elementos visuales y matemáticos exactos en island.html:
     - Renderizador Canvas 2D Superellipsoid (EXP 2.7, mochiPath).
     - Cuadrícula 2x2 de los 4 Mini-Mochis (mini0..mini3 con colores Coucou).
     - Tarjeta de Permisos idéntica a Screenshot 1 (Deny N, Allow Y, Always, command box).
     - Vista de Chat idéntica a Screenshot 2 (chat-bar, chat-input, send-btn con flecha arriba).
     - Píldora compacta idéntica a Screenshot 3 (pill, pillMochiCanvas, mini-grid).
"""
import unittest
from pathlib import Path
from jev.ui.island import IslandBridge, COLLAPSED_SIZE, EXPANDED_SIZE

BASE = Path(__file__).resolve().parent.parent


class FakeJarvisChat:
    def __init__(self):
        self.executed_tasks = []
        self.executed_images = []
        self._voice_enabled = False
        self._island_mode = True
        self._agent = type("Agent", (), {"messages": [
            {"role": "user", "content": "Hola Mochi"},
            {"role": "assistant", "content": "¡Hola! Estoy listo para ayudarte."}
        ]})()

    def execute_task(self, task: str):
        self.executed_tasks.append(task)

    def execute_task_with_image(self, task: str, image_b64: str):
        self.executed_images.append((task, image_b64))

    def activity_snapshot(self):
        return {"state": "idle", "pending": None}

    def resolve_approval(self, allow: bool):
        return {"ok": True, "allow": allow}


class TestCoucouMochiParity(unittest.TestCase):
    def setUp(self):
        self.jarvis = FakeJarvisChat()
        self.bridge = IslandBridge()
        self.bridge.attach(self.jarvis, None, None)

    def test_send_chat_triggers_task(self):
        res = self.bridge.send_chat("Analiza el sistema")
        self.assertTrue(res["ok"])

    def test_send_chat_empty_rejected(self):
        res = self.bridge.send_chat("   ")
        self.assertFalse(res["ok"])
        self.assertIn("error", res)

    def test_send_file_drop_text(self):
        res = self.bridge.send_file_drop("script.py", "print('hello')", "Revisa este script")
        self.assertTrue(res["ok"])

    def test_send_file_drop_image(self):
        res = self.bridge.send_file_drop("captura.png", "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA", "Qué ves?")
        self.assertTrue(res["ok"])

    def test_get_chat_history(self):
        hist = self.bridge.get_chat_history()
        self.assertTrue(hist["ok"])
        self.assertEqual(len(hist["messages"]), 2)
        self.assertEqual(hist["messages"][0]["content"], "Hola Mochi")

    def test_island_html_contains_coucou_mochi_engine(self):
        html = (BASE / "jev" / "ui" / "templates" / "island.html").read_text(encoding="utf-8")
        # Motor Superellipsoid exponente 2.7
        self.assertIn("EXP = 2.7", html)
        self.assertIn("mochiPath", html)
        self.assertIn("BotEngine", html)

        # 4 Mini-Mochis (Screenshot 3)
        self.assertIn('id="mini-grid"', html)
        self.assertIn('id="mini0"', html)
        self.assertIn('id="mini1"', html)
        self.assertIn('id="mini2"', html)
        self.assertIn('id="mini3"', html)
        self.assertIn("#2DD4BF", html) # Green
        self.assertIn("#F59E0B", html) # Orange
        self.assertIn("#8B5CF6", html) # Purple
        self.assertIn("#EF4444", html) # Red

        # Tarjeta de Permisos (Screenshot 1)
        self.assertIn('id="approvalCard"', html)
        self.assertIn('id="approvalCmd"', html)
        self.assertIn('id="denyBtn"', html)
        self.assertIn('id="allowBtn"', html)
        self.assertIn('id="alwaysBtn"', html)
        self.assertIn('>Denegar<', html)
        self.assertIn('>Permitir<', html)
        self.assertIn('>Siempre<', html)

        # Chat Integrado (Screenshot 2)
        self.assertIn('id="chatView"', html)
        self.assertIn('id="chatInput"', html)
        self.assertIn('id="chatSendBtn"', html)
        self.assertIn('placeholder="Pregúntale algo a JEV..."', html)

        # Drop Zone
        self.assertIn('id="dropView"', html)
        self.assertIn("Suelta tus archivos aquí", html)


if __name__ == "__main__":
    unittest.main()
