"""
Pruebas de la Isla de escritorio de JEV (compañero flotante estilo Coucou).

Cubren:
  * la API que consume la interfaz (estado, expandir/contraer, acciones),
  * la puerta de aprobación de acciones sensibles (permitir/denegar/timeout),
  * la coherencia de los recursos de la isla y del punto de entrada de escritorio.
"""
from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from app import JarvisBridge
from jev.ui import island as island_module
from jev.ui.island import COLLAPSED_SIZE, EXPANDED_SIZE, IslandBridge, compute_position

BASE = Path(__file__).resolve().parent.parent


class FakeWindow:
    def __init__(self) -> None:
        self.resized = []
        self.moved = []
        self.shown = 0
        self.hidden = 0

    def resize(self, width: int, height: int, fix_point=None) -> None:
        self.resized.append((width, height))

    def move(self, x: int, y: int) -> None:
        self.moved.append((x, y))

    def show(self) -> None:
        self.shown += 1

    def hide(self) -> None:
        self.hidden += 1

    def restore(self) -> None:
        pass

    def destroy(self) -> None:
        self.shown = -999


class FakeJarvis:
    _voice_enabled = False
    _island_mode = False

    def __init__(self) -> None:
        self.stopped = False
        self.risky = False
        self.resolved = []

    def activity_snapshot(self):
        return {"state": "idle", "tool": "", "pending": None}

    def stop_agent(self) -> None:
        self.stopped = True

    def toggle_voice_synthesis(self, enabled: bool) -> None:
        self._voice_enabled = bool(enabled)

    def set_confirm_risky(self, enabled: bool) -> bool:
        self.risky = bool(enabled)
        return self.risky

    def resolve_approval(self, allow: bool):
        self.resolved.append(bool(allow))
        return {"ok": True, "allow": bool(allow)}


class TestIslandBridgeAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.jarvis = FakeJarvis()
        self.main = FakeWindow()
        self.island = FakeWindow()
        self.bridge = IslandBridge()
        self.bridge.attach(self.jarvis, self.main, self.island, {"quitting": False})

    def test_attach_marks_island_mode(self):
        self.assertTrue(self.jarvis._island_mode)

    def test_get_status_without_jarvis(self):
        empty = IslandBridge().get_status()
        self.assertEqual(empty["state"], "idle")
        self.assertIsNone(empty["pending"])
        self.assertIn("model", empty)

    def test_expand_and_collapse_resize_window(self):
        self.bridge.expand()
        self.assertEqual(self.island.resized[-1], EXPANDED_SIZE)
        self.bridge.collapse()
        self.assertEqual(self.island.resized[-1], COLLAPSED_SIZE)
        self.assertTrue(all(isinstance(x, int) and isinstance(y, int) for x, y in self.island.moved))

    def test_open_main_shows_window(self):
        self.bridge.open_main()
        self.assertEqual(self.main.shown, 1)

    def test_toggle_voice_roundtrip(self):
        first = self.bridge.toggle_voice()
        self.assertTrue(first["enabled"])
        self.assertTrue(self.jarvis._voice_enabled)
        second = self.bridge.toggle_voice()
        self.assertFalse(second["enabled"])

    def test_safe_mode_toggle(self):
        result = self.bridge.set_confirm_risky(True)
        self.assertTrue(result["enabled"])
        self.assertTrue(self.jarvis.risky)

    def test_resolve_approval_delegates(self):
        result = self.bridge.resolve_approval(False)
        self.assertTrue(result["ok"])
        self.assertEqual(self.jarvis.resolved, [False])

    def test_stop_agent(self):
        self.bridge.stop_agent()
        self.assertTrue(self.jarvis.stopped)

    def test_quit_destroys_windows_and_flags_state(self):
        state = {"quitting": False}
        self.bridge._quit_state = state
        fake = FakeWindow()
        with mock.patch.object(island_module.webview, "windows", [fake, self.island]):
            self.bridge.quit_app()
        self.assertTrue(state["quitting"])
        self.assertEqual(fake.shown, -999)

    def test_get_cursor_returns_valid_dict(self):
        cursor = self.bridge.get_cursor()
        self.assertIsInstance(cursor, dict)
        for key in ("cx", "cy", "wx", "wy", "ww", "wh"):
            self.assertIn(key, cursor)
            self.assertIsInstance(cursor[key], int)

    def test_get_chat_history_from_jarvis_history(self):
        self.jarvis._chat_history = [
            {"role": "user", "content": "hola mochi"},
            {"role": "assistant", "content": "¡Hola! ¿Cómo estás?"}
        ]
        history = self.bridge.get_chat_history()
        self.assertTrue(history["ok"])
        self.assertEqual(len(history["messages"]), 2)
        self.assertEqual(history["messages"][0]["role"], "user")
        self.assertEqual(history["messages"][1]["content"], "¡Hola! ¿Cómo estás?")


class TestIslandGeometry(unittest.TestCase):
    def test_collapsed_and_expanded_are_consistent(self):
        self.assertLess(COLLAPSED_SIZE[0], EXPANDED_SIZE[0])
        self.assertLess(COLLAPSED_SIZE[1], EXPANDED_SIZE[1])

    def test_compute_position_returns_centered_int(self):
        x, y = compute_position(COLLAPSED_SIZE[0])
        self.assertIsInstance(x, int)
        self.assertIsInstance(y, int)
        self.assertGreaterEqual(x, 0)
        self.assertEqual(y, 0)


class TestApprovalGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bridge = JarvisBridge()

    def tearDown(self) -> None:
        self.bridge.set_confirm_risky(False)
        self.bridge._pending_approval = None

    def _run_tool_call(self, tool: str, args: dict):
        result = {}

        def worker():
            result["approved"] = self.bridge._on_tool_call(tool, args)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        for _ in range(40):
            if self.bridge.pending_approval():
                break
            time.sleep(0.05)
        return thread, result

    def test_no_approval_when_disabled(self):
        self.bridge.set_confirm_risky(False)
        self.assertTrue(self.bridge._on_tool_call("execute_command", {"command": "echo hola"}))
        self.assertIsNone(self.bridge.pending_approval())

    def test_allow_unblocks_tool_call(self):
        self.bridge.set_confirm_risky(True)
        thread, result = self._run_tool_call("execute_command", {"command": "git push origin main"})
        pending = self.bridge.pending_approval()
        self.assertIsNotNone(pending)
        self.assertEqual(pending["tool"], "execute_command")
        self.assertEqual(self.bridge.activity_snapshot()["state"], "approval")
        self.bridge.resolve_approval(True)
        thread.join(timeout=3)
        self.assertTrue(result.get("approved"))
        self.assertIsNone(self.bridge.pending_approval())

    def test_deny_vetoes_tool_call(self):
        self.bridge.set_confirm_risky(True)
        thread, result = self._run_tool_call("write_file", {"path": "x.txt", "content": "hola"})
        self.assertIsNotNone(self.bridge.pending_approval())
        self.bridge.resolve_approval(False)
        thread.join(timeout=3)
        self.assertFalse(result.get("approved"))
        self.assertIn("denegada", self.bridge._last_thought.lower())

    def test_timeout_denies_and_clears_pending(self):
        self.bridge.set_confirm_risky(True)
        allowed = self.bridge._request_approval("execute_command", {"command": "dir"}, timeout=0.7)
        self.assertFalse(allowed)
        self.assertIsNone(self.bridge.pending_approval())

    def test_activity_snapshot_reflects_tool_state(self):
        self.bridge.set_confirm_risky(False)
        self.bridge._agent.is_running = True
        self.bridge._tool_in_progress = True
        try:
            snapshot = self.bridge.activity_snapshot()
            self.assertEqual(snapshot["state"], "tool")
        finally:
            self.bridge._agent.is_running = False
            self.bridge._tool_in_progress = False


class TestIslandAssets(unittest.TestCase):
    def test_island_html_has_required_hooks(self):
        html = (BASE / "jev" / "ui" / "templates" / "island.html").read_text(encoding="utf-8")
        for hook in ('id="pill"', 'id="activityText"', 'id="approvalCard"',
                     'id="allowBtn"', 'id="denyBtn"', 'get_status',
                     'get_cursor', 'startChatWatcher', 'typing-dot',
                     'data-state', 'compactState'):
            with self.subTest(hook=hook):
                self.assertIn(hook, html)

    def test_desktop_entry_imports_without_starting_gui(self):
        import jev_desktop

        self.assertTrue(callable(jev_desktop.main))

    def test_launcher_defaults_to_island(self):
        source = (BASE / "jev_launcher.py").read_text(encoding="utf-8")
        self.assertIn("jev_desktop", source)
        self.assertIn("--classic", source)


if __name__ == "__main__":
    unittest.main()
