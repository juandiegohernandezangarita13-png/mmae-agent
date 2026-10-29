"""
Pruebas funcionales y de arquitectura para el Agente Autónomo Autorreflexivo y Autoevolutivo en Caliente.
Valida que ante una tarea sin soporte previo (e.g. WhatsApp, consulta de red),
el agente no aborte, reflexione, sintetice código, lo cargue en caliente y culmine la tarea con éxito.
"""
import unittest
import tempfile
import shutil
from pathlib import Path

from jev.core.self_evolving_agent import SelfEvolvingAgent
from jev.tools.base import ToolRegistry


class TestSelfEvolvingRuntimeAgent(unittest.TestCase):
    def setUp(self):
        self.temp_workspace = Path(tempfile.mkdtemp())
        self.events_log = []

        def event_tracker(event_type, data):
            self.events_log.append({"event": event_type, "data": data})

        self.agent = SelfEvolvingAgent(
            registry=ToolRegistry(),
            workspace_dir=self.temp_workspace,
            on_event=event_tracker
        )

    def tearDown(self):
        shutil.rmtree(self.temp_workspace, ignore_errors=True)

    def test_whatsapp_task_autoevolution_and_completion(self):
        """
        Caso de prueba: Se ordena enviar un mensaje por WhatsApp sin soporte previo.
        El agente debe reflexionar, sintetizar el gateway, cargarlo en caliente y enviar el mensaje.
        """
        # La herramienta no existe al inicio
        self.assertIsNone(self.agent.registry.get("send_whatsapp_message_tool"))

        task_goal = "Enviar confirmación de pedido por WhatsApp al cliente"
        required_tool = "send_whatsapp_message_tool"
        args = {
            "recipient": "+34600112233",
            "message": "Hola, tu pedido #9842 ha sido procesado exitosamente."
        }

        # Ejecución autónoma
        result = self.agent.run_task(
            task_goal=task_goal,
            required_capability=required_tool,
            task_args=args
        )

        # 1. Verificar culminación exitosa sin abortar
        self.assertTrue(result["success"])
        self.assertTrue(result["evolved"])
        self.assertEqual(result["tool_synthesized"], "send_whatsapp_message_tool")
        self.assertIn("WhatsApp Gateway", result["output"])
        self.assertIn("+34600112233", result["output"])

        # 2. Verificar que se ejecutó el monólogo de autorreflexión
        reflection_events = [e for e in self.events_log if e["event"] == "reflection"]
        self.assertGreaterEqual(len(reflection_events), 1)
        monologue_text = reflection_events[0]["data"]
        self.assertIn("MONÓLOGO DE AUTORREFLEXIÓN", monologue_text)
        self.assertIn("¿Qué interfaz o protocolo necesito para cumplir este paso?", monologue_text)

        # 3. Verificar que la herramienta quedó inyectada en memoria (hot-reload)
        injected = self.agent.registry.get("send_whatsapp_message_tool")
        self.assertIsNotNone(injected)

        # 4. Verificar memoria técnica a largo plazo (código persistido en ./generated_tools/)
        expected_file = self.temp_workspace / "generated_tools" / "send_whatsapp_message_tool.py"
        self.assertTrue(expected_file.exists())
        code_content = expected_file.read_text(encoding="utf-8")
        self.assertIn("class SendWhatsappMessageTool", code_content)

        # 5. Segunda invocación: debe resolverse inmediatamente sin re-evolucionar
        second_result = self.agent.run_task(
            task_goal="Enviar segundo mensaje",
            required_capability="send_whatsapp_message_tool",
            task_args={"recipient": "+34600998877", "message": "Segundo mensaje"}
        )
        self.assertTrue(second_result["success"])
        self.assertFalse(second_result["evolved"])  # Usó la herramienta ya residente en memoria

    def test_network_lookup_autoevolution(self):
        """
        Caso de prueba: Se ordena una consulta de red sin herramienta previa.
        """
        task_goal = "Inspeccionar IP de localhost para diagnóstico"
        required_tool = "network_dns_lookup_tool"
        args = {"target_host": "localhost"}

        result = self.agent.run_task(
            task_goal=task_goal,
            required_capability=required_tool,
            task_args=args
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["evolved"])
        self.assertIn("127.0.0.1", result["output"])


if __name__ == "__main__":
    unittest.main()
