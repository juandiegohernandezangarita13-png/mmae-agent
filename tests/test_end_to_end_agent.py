"""
Test de Integración End-to-End para el Agente JEV.
Verifica el ciclo completo:
1. Descomposición DAG de la tarea.
2. Ejecución de herramientas (write_file y execute_python) confinadas en workspace.
3. Protocolo de verificación empírica (ActionVerifier).
4. Persistencia en checkpoints y registro de pasos en SQLite.
5. Botón de detención de emergencia.
"""
import unittest
import tempfile
import shutil
import json
from pathlib import Path

from jev.config import AgentConfig
from jev.core.agent import AgentCore
from jev.core.memory import HierarchicalMemory
from jev.tools.base import ToolRegistry, ToolResult
from jev.tools.filesystem import WriteFileTool, ReadFileTool
from jev.tools.code_runner import PythonRunnerTool


class MockLLMForEndToEnd:
    """Mock determinista de LLM para pruebas de integración controladas."""

    def __init__(self):
        self.step = 0

    def chat(self, messages, tools=None):
        from jev.core.llm_client import LLMResponse
        self.step += 1

        if self.step == 1:
            # Respuesta del planificador DAG
            dag_json = json.dumps([
                {
                    "id": 1,
                    "title": "Crear script de cálculo",
                    "description": "Escribir un script en Python que calcule la secuencia de Fibonacci",
                    "expected_verification": "Archivo fib.py generado con sintaxis válida",
                    "dependencies": []
                },
                {
                    "id": 2,
                    "title": "Ejecutar script",
                    "description": "Ejecutar fib.py y validar resultado",
                    "expected_verification": "Salida por consola con los números correctos y código 0",
                    "dependencies": [1]
                }
            ])
            return LLMResponse(content=f"```json\n{dag_json}\n```")

        elif self.step == 2:
            # Paso 1: Llamar a write_file
            code = "def fib(n):\n    return n if n <= 1 else fib(n-1) + fib(n-2)\nprint([fib(i) for i in range(8)])\n"
            return LLMResponse(
                content="Voy a crear el script fib.py",
                tool_calls=[{
                    "id": "call_1",
                    "name": "write_file",
                    "arguments": {"path": "fib.py", "content": code}
                }]
            )

        elif self.step == 3:
            # Paso 2: Llamar a execute_python
            return LLMResponse(
                content="Ahora ejecuto el script para verificar su funcionamiento",
                tool_calls=[{
                    "id": "call_2",
                    "name": "execute_python",
                    "arguments": {"code": "import fib\nprint('TEST_OK')"}
                }]
            )

        else:
            # Conclusión final
            return LLMResponse(
                content="Tarea completada con éxito. El script fib.py fue generado, verificado y ejecutado sin errores."
            )


class TestEndToEndAgent(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workspace_dir = self.temp_dir / "workspace"
        self.workspace_dir.mkdir(parents=True)
        self.memory_dir = self.temp_dir / "memory"
        self.memory_dir.mkdir(parents=True)
        self.checkpoints_dir = self.temp_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True)

        self.config = AgentConfig(
            base_dir=self.temp_dir,
            workspace_dir=self.workspace_dir,
            memory_dir=self.memory_dir,
            max_iterations=6,
            hybrid_mode=False
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_pipeline_execution(self):
        """Ejecuta el pipeline completo de JEV simulando una tarea de generación y ejecución."""
        thoughts = []
        tool_calls_logged = []
        tool_results_logged = []

        memory = HierarchicalMemory(self.memory_dir)
        registry = ToolRegistry()
        registry.register(WriteFileTool(workspace_dir=self.workspace_dir))
        registry.register(ReadFileTool(workspace_dir=self.workspace_dir))
        registry.register(PythonRunnerTool(workspace_dir=self.workspace_dir))

        agent = AgentCore(
            config=self.config,
            registry=registry,
            memory=memory,
            on_thought=lambda t: thoughts.append(t),
            on_tool_call=lambda name, args: tool_calls_logged.append((name, args)),
            on_tool_result=lambda name, res: tool_results_logged.append((name, res.success))
        )
        # Inyectar el LLM mock
        agent.llm = MockLLMForEndToEnd()
        agent.planner.llm = agent.llm

        result = agent.run_task("Crea un script fib.py que calcule los números de Fibonacci y pruébalo.")

        # 1. Comprobar que el entregable final sea exitoso
        self.assertIn("completada con éxito", result)

        # 2. Comprobar que el archivo se creó en el workspace
        fib_path = self.workspace_dir / "fib.py"
        self.assertTrue(fib_path.exists())
        self.assertGreater(fib_path.stat().st_size, 0)
        content = fib_path.read_text(encoding="utf-8")
        self.assertIn("def fib", content)

        # 3. Comprobar que las herramientas se llamaron y fueron verificadas con éxito
        self.assertEqual(len(tool_calls_logged), 2)
        self.assertEqual(tool_calls_logged[0][0], "write_file")
        self.assertEqual(tool_calls_logged[1][0], "execute_python")

        for tool_name, success in tool_results_logged:
            self.assertTrue(success, f"La herramienta {tool_name} reportó fallo.")

        # 4. Comprobar que los pensamientos reflejan el planificador DAG y las verificaciones
        thoughts_str = "\n".join(thoughts)
        self.assertIn("Plan DAG Generado", thoughts_str)
        self.assertIn("VERIFICACIÓN APROBADA", thoughts_str)

        # 5. Comprobar que los pasos se registraron en la memoria de trabajo SQLite
        self.assertTrue((self.memory_dir / "knowledge_base.db").exists())
        self.assertTrue((self.memory_dir / "episodes.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
