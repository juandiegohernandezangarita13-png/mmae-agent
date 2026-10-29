"""
Suite de Pruebas Unitarias para Resiliencia del Cliente LLM,
Gestión de Timeouts Granulares, Persistencia en VRAM (keep_alive),
Poda de Contexto y Reintentos con Backoff Exponencial.
"""
import unittest
from unittest.mock import MagicMock, patch
import httpx

from jev.config import AgentConfig
from jev.core.llm_client import LocalLLMClient, LLMResponse
from jev.core.agent import AgentCore
from jev.core.planner import TaskPlan, SubTask


class TestLLMResilienceAndTimeout(unittest.TestCase):

    def setUp(self):
        self.config = AgentConfig(
            llm_provider="ollama",
            connect_timeout=10.0,
            read_timeout=300.0,
            ollama_keep_alive="30m",
            llm_max_retries=2,
            hybrid_mode=False,
            model_name="qwen2.5-coder:latest",
            fallback_models=["qwen2.5-coder:latest"]
        )
        self.client = LocalLLMClient(self.config)

    def test_granular_timeouts_configuration(self):
        """Verifica que connect_timeout = 10.0s y read_timeout >= 300.0s estén desacoplados."""
        self.assertEqual(self.client.connect_timeout, 10.0)
        self.assertGreaterEqual(self.client.read_timeout, 300.0)
        self.assertEqual(self.client.timeout.connect, 10.0)
        self.assertEqual(self.client.timeout.read, 300.0)

    def test_keep_alive_injection_in_ollama_payload(self):
        """Verifica que el parámetro keep_alive = '30m' se inyecte en el payload para Ollama."""
        with patch("httpx.Client.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "Respuesta simulada"}}]
            }
            mock_post.return_value = mock_resp

            res = self.client.chat(messages=[{"role": "user", "content": "hola"}])
            self.assertEqual(res.content, "Respuesta simulada")
            self.assertTrue(mock_post.called)

            called_kwargs = mock_post.call_args[1]
            payload = called_kwargs.get("json", {})
            self.assertEqual(payload.get("keep_alive"), "30m")
            self.assertEqual(payload.get("model"), "qwen2.5-coder:latest")

    def test_prune_messages_for_local_inference(self):
        """Verifica que tool outputs sobredimensionados en turnos intermedios sean podados."""
        huge_tool_output = "X" * 5000
        messages = [
            {"role": "system", "content": "Prompt de sistema"},
            {"role": "user", "content": "Meta original"},
            {"role": "assistant", "content": "Llamando herramienta"},
            {"role": "tool", "content": huge_tool_output},
            {"role": "assistant", "content": "Segunda llamada"},
            {"role": "tool", "content": "Salida corta"},
            {"role": "user", "content": "Siguiente instrucción"}
        ]

        pruned = self.client._prune_messages_for_local_inference(messages, max_tool_chars=500)
        # El sistema y la meta inicial se preservan intactos
        self.assertEqual(pruned[0]["content"], "Prompt de sistema")
        self.assertEqual(pruned[1]["content"], "Meta original")
        # El mensaje de herramienta intermedio gigante debe haber sido truncado
        tool_msg = [m for m in pruned if m.get("role") == "tool" and "Truncado" in m.get("content", "")][0]
        self.assertLess(len(tool_msg["content"]), 1000)
        self.assertIn("Truncado", tool_msg["content"])

    def test_retry_with_exponential_backoff_on_read_timeout(self):
        """Verifica que ante ReadTimeout o error 504 se reintente con backoff exponencial antes de fallar."""
        mock_sleep = MagicMock()
        self.client._sleep_fn = mock_sleep

        with patch("httpx.Client.post") as mock_post:
            # Fallar 2 veces por timeout y responder exitosamente en el 3er intento
            mock_success = MagicMock()
            mock_success.status_code = 200
            mock_success.json.return_value = {
                "choices": [{"message": {"content": "Éxito tras reintentos"}}]
            }
            mock_post.side_effect = [
                httpx.ReadTimeout("timed out"),
                httpx.ReadTimeout("timed out"),
                mock_success
            ]

            res = self.client.chat(messages=[{"role": "user", "content": "test retry"}])
            self.assertEqual(res.content, "Éxito tras reintentos")
            # Se deben haber realizado 3 llamadas (2 fallos + 1 éxito)
            self.assertEqual(mock_post.call_count, 3)
            # _sleep_fn debe haberse invocado 2 veces con backoff
            self.assertEqual(mock_sleep.call_count, 2)
            self.assertGreater(mock_sleep.call_args_list[0][0][0], 0)

    def test_dag_context_pruning_on_subtask_progression(self):
        """Verifica que el agente sintetice dependencias y pode el contexto al despachar subtareas."""
        agent = AgentCore(config=self.config)
        t1 = SubTask(
            id=1,
            title="Escanear puertos",
            description="Ejecutar escaneo",
            expected_verification="Puertos hallados",
            status="completed",
            output_summary="Puertos 80 y 443 abiertos"
        )
        t2 = SubTask(
            id=2,
            title="Generar reporte",
            description="Crear reporte",
            expected_verification="Archivo reporte.md",
            status="in_progress",
            dependencies=[1]
        )
        plan = TaskPlan(goal="Auditoría", tasks=[t1, t2])

        # Simular historial largo acumulado
        agent.messages = [
            {"role": "system", "content": "SYSTEM_PROMPT"},
            {"role": "user", "content": "GOAL_PROMPT"},
            {"role": "assistant", "content": "Thought 1"},
            {"role": "tool", "content": "Log largo 1" * 50},
            {"role": "assistant", "content": "Thought 2"},
            {"role": "tool", "content": "Log largo 2" * 50},
            {"role": "assistant", "content": "Thought 3"},
            {"role": "tool", "content": "Log largo 3" * 50},
            {"role": "assistant", "content": "Thought 4"},
            {"role": "tool", "content": "Log largo 4" * 50}
        ]

        agent._prune_context_for_subtask(t2, plan)

        # Debe contener el sistema, la meta y el bloque de síntesis de dependencias
        self.assertEqual(agent.messages[0]["content"], "SYSTEM_PROMPT")
        self.assertEqual(agent.messages[1]["content"], "GOAL_PROMPT")
        summary_msg = agent.messages[2]["content"]
        self.assertIn("Dependencia Directa", summary_msg)
        self.assertIn("Puertos 80 y 443 abiertos", summary_msg)
        self.assertIn("MICRO-TAREA DAG ACTIVA #2", summary_msg)


if __name__ == "__main__":
    unittest.main()
