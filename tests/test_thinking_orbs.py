"""
Suite de Pruebas Unitarias para el Visualizador de Estado Cognitivo "Thinking Orbs" en la GUI de JEV:
1. Integración en jarvis.html del contenedor del orbe y canvas nativo.
2. Declaración de estados reactivos (STATE_IDLE, STATE_THINKING, STATE_TOOL_EXEC, STATE_SPEAKING, STATE_ERROR).
3. Soporte de accesibilidad para prefers-reduced-motion.
4. Controlador global window.setAgentOrbState y método transitionTo.
5. Sincronización en JarvisBridge (app.py) para control de estados del orbe.
"""
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app import JarvisBridge
from jev.config import AgentConfig


class TestThinkingOrbsTemplate(unittest.TestCase):
    """Pruebas de presencia, estructura y sintaxis del Orbe en la plantilla HTML."""

    @classmethod
    def setUpClass(cls):
        template_path = Path(__file__).parent.parent / "jev" / "ui" / "templates" / "jarvis.html"
        cls.html_content = template_path.read_text(encoding="utf-8")

    def test_container_and_canvas_elements_present(self):
        """Verifica que el contenedor y el canvas del orbe existan en la cabecera."""
        self.assertIn('id="thinking-orb-container"', self.html_content)
        self.assertIn('id="thinkingOrbCanvas"', self.html_content)
        self.assertIn('class="thinking-orb-container"', self.html_content)
        self.assertIn('class="thinking-orb-canvas"', self.html_content)

    def test_prefers_reduced_motion_accessibility(self):
        """Verifica que se respete prefers-reduced-motion tanto en CSS como en JavaScript."""
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.html_content)
        self.assertIn("prefers-reduced-motion", self.html_content)

    def test_reactive_states_declared(self):
        """Verifica la definición de los 5 estados cognitivos requeridos."""
        required_states = [
            "STATE_IDLE",
            "STATE_THINKING",
            "STATE_TOOL_EXEC",
            "STATE_SPEAKING",
            "STATE_ERROR"
        ]
        for state in required_states:
            self.assertIn(state, self.html_content, f"El estado {state} debe estar declarado")

    def test_window_set_agent_orb_state_controller(self):
        """Verifica la implementación exacta del controlador window.setAgentOrbState."""
        self.assertIn("window.setAgentOrbState = function", self.html_content)
        self.assertIn("orb.transitionTo", self.html_content)
        self.assertIn("orb.dataset.state = stateName", self.html_content)

    def test_thinking_orb_class_present(self):
        """Verifica la existencia de la clase y el inicializador de animación."""
        self.assertIn("class ThinkingOrb", self.html_content)
        self.assertIn("initThinkingOrb()", self.html_content)

    def test_event_callbacks_wire_orb_states(self):
        """Verifica que los callbacks del backend disparen transiciones del orbe."""
        self.assertIn("window.setAgentOrbState(STATE_THINKING)", self.html_content)
        self.assertIn("window.setAgentOrbState(STATE_TOOL_EXEC)", self.html_content)
        self.assertIn("window.setAgentOrbState(STATE_ERROR)", self.html_content)
        self.assertIn("window.setAgentOrbState(STATE_SPEAKING)", self.html_content)
        self.assertIn("window.setAgentOrbState(STATE_IDLE)", self.html_content)


class TestThinkingOrbsBridge(unittest.TestCase):
    """Pruebas del método set_orb_state en JarvisBridge."""

    def setUp(self):
        cfg = AgentConfig()
        self.bridge = JarvisBridge(cfg)
        self.bridge._eval_js = MagicMock()

    def test_bridge_set_orb_state_idle(self):
        """Verifica que set_orb_state('idle') evalúe JavaScript en el frontend."""
        self.bridge.set_orb_state("idle")
        self.bridge._eval_js.assert_called_once()
        call_arg = self.bridge._eval_js.call_args[0][0]
        self.assertIn("window.setAgentOrbState", call_arg)
        self.assertIn('"idle"', call_arg)

    def test_bridge_set_orb_state_all_variations(self):
        """Verifica el despacho de todos los estados desde el backend."""
        states = ["STATE_THINKING", "STATE_TOOL_EXEC", "STATE_SPEAKING", "STATE_ERROR", "STATE_IDLE"]
        for st in states:
            self.bridge._eval_js.reset_mock()
            self.bridge.set_orb_state(st)
            self.bridge._eval_js.assert_called_once()
            call_arg = self.bridge._eval_js.call_args[0][0]
            self.assertIn(f'"{st}"', call_arg)


if __name__ == "__main__":
    unittest.main()
