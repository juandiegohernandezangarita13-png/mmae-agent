"""
Pruebas unitarias para el control de bucles repetitivos y reglas de apertura de apps en Windows.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from jev.core.agent import AgentCore
from jev.core.llm_client import LLMResponse
from jev.tools.base import ToolRegistry, BaseTool, ToolResult


class DummyTool(BaseTool):
    name = "execute_command"
    description = "Dummy command tool"
    parameters = {"type": "object", "properties": {"command": {"type": "string"}}}

    def execute(self, command: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, output=f"Executed: {command}")


class TestLoopControlAndWindowsApps(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(DummyTool())
        self.agent = AgentCore(registry=self.registry)

    def test_01_system_prompt_has_windows_apps_protocols(self):
        """Verifica que el System Prompt contenga las reglas explícitas de apps de Windows y WhatsApp."""
        prompt = self.agent._build_system_prompt()
        self.assertIn("whatsapp:", prompt.lower())
        self.assertIn("web.whatsapp.com", prompt.lower())
        self.assertIn("ms-settings:appsfeatures", prompt)
        self.assertIn("ctrl + f", prompt.lower())
        self.assertIn("keyboard_type", prompt)
        self.assertIn("inspect_screen_ui", prompt)
        self.assertIn("CONTROL DE BUCLES Y ACCIONES REPETITIVAS", prompt)

    def test_02_loop_control_two_consecutive_attempts_injects_strict_warning(self):
        """
        Verifica que al repetir una acción bloqueada por deduplicación 2 veces seguidas,
        se inyecte el mensaje de error estricto prohibiendo la llamada.
        """
        # Simulamos que la acción ya está en memoria de trabajo
        session_id = "task_12345"
        self.agent.memory.record_step(
            session_id=session_id,
            step_num=1,
            tool_name="execute_command",
            args={"command": "start edge ms-settings:appsfeatures"},
            success=True
        )

        mock_tc = {
            "id": "call_rep_1",
            "name": "execute_command",
            "arguments": {"command": "start edge ms-settings:appsfeatures"}
        }

        # Intento 1: Devuelve aviso de deduplicación
        # Intento 2: Inyecta mensaje estricto de ACCION CANCELADA
        # Intento 3: Termina
        call_count = 0

        def mock_chat(*args, **kwargs):
            nonlocal call_count
            if not kwargs.get("tools"):
                return LLMResponse(content='[{"id": 1, "title": "Test", "description": "Test", "expected_verification": "ok", "dependencies": []}]')
            call_count += 1
            if call_count <= 2:
                return LLMResponse(
                    content="",
                    tool_calls=[mock_tc]
                )
            else:
                return LLMResponse(
                    content="Cambiando estrategia.",
                    tool_calls=[]
                )

        self.agent.llm.chat = MagicMock(side_effect=mock_chat)

        with patch("time.time", return_value=12345):
            res = self.agent.run_task("Abrir whatsapp")

        # Buscar el mensaje estricto inyectado en el historial de mensajes
        tool_messages = [m for m in self.agent.messages if m.get("role") == "tool"]
        self.assertGreaterEqual(len(tool_messages), 2)

        # Mensaje 1: deduplicación normal
        self.assertIn("omitida por deduplicación", tool_messages[0]["content"])

        # Mensaje 2: advertencia estricta con prohibición
        self.assertIn("ACCION CANCELADA", tool_messages[1]["content"])
        self.assertIn("Tienes PROHIBIDO volver a llamar a execute_command con esos argumentos", tool_messages[1]["content"])
        self.assertIn("Plantea una estrategia completamente distinta", tool_messages[1]["content"])

    def test_03_loop_control_three_consecutive_attempts_aborts_task(self):
        """
        Verifica que al insistir 3 veces en la misma acción bloqueada,
        la tarea se aborte inmediatamente marcándola como fallida.
        """
        session_id = "task_99999"
        self.agent.memory.record_step(
            session_id=session_id,
            step_num=1,
            tool_name="execute_command",
            args={"command": "start edge ms-settings:appsfeatures"},
            success=True
        )

        mock_tc = {
            "id": "call_rep_loop",
            "name": "execute_command",
            "arguments": {"command": "start edge ms-settings:appsfeatures"}
        }

        # LLM insiste obstinadamente en el mismo tool_call
        def mock_chat_insist(*args, **kwargs):
            return LLMResponse(
                content="",
                tool_calls=[mock_tc]
            )

        self.agent.llm.chat = MagicMock(side_effect=mock_chat_insist)

        with patch("time.time", return_value=99999):
            res = self.agent.run_task("Abrir whatsapp")

        # Verificar que la tarea fue abortada como fallida
        self.assertIn("ACCION CANCELADA", res)
        self.assertIn("3 veces", res)
        self.assertIn("liberar la interfaz", res)

    def test_04_procedural_memory_seed_for_whatsapp(self):
        """Verifica que la memoria procedimental contenga la solución semántica para WhatsApp."""
        solutions = self.agent.memory.search_solutions("whatsapp abrir mensaje")
        self.assertGreater(len(solutions), 0)
        sol = solutions[0]
        self.assertIn("whatsapp", sol["trigger_keywords"])
        self.assertIn("Start-Process", sol["solution_summary"])

    def test_05_ultra_concise_system_prompt_rules(self):
        """Verifica las directivas de concisión extrema y baja latencia en el System Prompt."""
        prompt = self.agent._build_system_prompt()
        self.assertIn("MODO EJECUTOR DE BAJA LATENCIA", prompt)
        self.assertIn("Sé un ejecutor de baja latencia", prompt)
        self.assertIn("no debe superar las 20 palabras", prompt)
        self.assertIn("Prohibido describir lo que vas a hacer en párrafos largos", prompt)
        self.assertIn("ejecuta la herramienta y deja que los resultados hablen", prompt)

    def test_06_live_steering_injection(self):
        """Verifica que la inyección de órdenes en caliente se incorpore a la memoria en tiempo real."""
        thought_logs = []
        self.agent.on_thought = lambda t: thought_logs.append(t)

        # Inyectar una orden del usuario en caliente
        user_feedback = "No uses Edge, abre directamente whatsapp web en Chrome"
        self.agent.inject_user_feedback(user_feedback)

        # Mock del LLM para finalizar tras recibir la orden
        def mock_chat(*args, **kwargs):
            return LLMResponse(content="Entendido, aplicando nueva orden.", tool_calls=[])

        self.agent.llm.chat = MagicMock(side_effect=mock_chat)

        with patch("time.time", return_value=88888):
            res = self.agent.run_task("Abrir whatsapp")

        # 1. Comprobar que la cola se vació
        self.assertTrue(self.agent.user_interrupt_queue.empty())

        # 2. Comprobar que el mensaje prioritario se inyectó en self.messages
        injected_msgs = [
            m for m in self.agent.messages 
            if m.get("role") == "user" and "[INSTRUCCIÓN PRIORITARIA DEL USUARIO EN TIEMPO REAL]" in m.get("content", "")
        ]
        self.assertEqual(len(injected_msgs), 1)
        self.assertIn(user_feedback, injected_msgs[0]["content"])

        # 3. Comprobar que el callback on_thought registró la intervención
        intervention_thoughts = [t for t in thought_logs if "Intervención del Usuario en Caliente" in t]
        self.assertGreaterEqual(len(intervention_thoughts), 1)
        self.assertIn(user_feedback, intervention_thoughts[0])

        # 4. Comprobar que is_running vuelve a False al finalizar
        self.assertFalse(self.agent.is_running)

    def test_07_conversational_intent_classification(self):
        """Verifica la correcta clasificación entre entradas de chat y tareas reales."""
        # Saludos y chat puro -> True
        self.assertTrue(self.agent.is_conversational_intent("hola"))
        self.assertTrue(self.agent.is_conversational_intent("¡Hola!"))
        self.assertTrue(self.agent.is_conversational_intent("hola JEV"))
        self.assertTrue(self.agent.is_conversational_intent("buenas tardes"))
        self.assertTrue(self.agent.is_conversational_intent("qué tal"))
        self.assertTrue(self.agent.is_conversational_intent("quién eres"))
        self.assertTrue(self.agent.is_conversational_intent("muchas gracias"))

        # Acciones o tareas con verbos de ejecución -> False
        self.assertFalse(self.agent.is_conversational_intent("hola, abre whatsapp"))
        self.assertFalse(self.agent.is_conversational_intent("crea un archivo de notas"))
        self.assertFalse(self.agent.is_conversational_intent("busca en google sobre IA"))
        self.assertFalse(self.agent.is_conversational_intent("ejecuta el script fib.py"))

    def test_08_conversational_direct_chat_no_tools(self):
        """Verifica que un saludo se responda directamente sin invocar herramientas ni DAG planner."""
        thought_logs = []
        self.agent.on_thought = lambda t: thought_logs.append(t)

        self.agent.llm.chat = MagicMock(return_value=LLMResponse(
            content="¡Hola! Soy JEV, tu asistente autónomo. ¿En qué te ayudo hoy?",
            tool_calls=[]
        ))

        # El DAG planner no debe ser llamado
        self.agent.planner.create_plan = MagicMock()

        res = self.agent.run_task("hola")

        self.assertIn("Soy JEV", res)
        self.agent.planner.create_plan.assert_not_called()
        self.assertTrue(any("Modo Chat Directo" in t for t in thought_logs))

        # Verificar que las llamadas al LLM no contenían herramientas
        self.agent.llm.chat.assert_called_once()
        _, kwargs = self.agent.llm.chat.call_args
        self.assertEqual(kwargs.get("tools"), [])

    def test_09_communication_and_completion_rules_in_system_prompt(self):
        """Verifica las reglas de comunicación directa y prohibición de keyboard_type para hablar al usuario."""
        prompt = self.agent._build_system_prompt()
        self.assertIn("COMUNICACIÓN CON EL USUARIO", prompt)
        self.assertIn("responde ÚNICAMENTE con texto directo en tu respuesta final", prompt)
        self.assertIn("Queda ESTRICTAMENTE PROHIBIDO usar 'keyboard_type'", prompt)
        self.assertIn("execute_python' con comandos print()", prompt)
        self.assertIn("CRITERIO DE FINALIZACIÓN", prompt)


if __name__ == "__main__":
    unittest.main()
