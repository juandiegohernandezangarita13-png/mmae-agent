"""
Pruebas unitarias para las capacidades de autonomía avanzada de JEV:
1. Memoria Semántica Vectorial (SemanticMemoryIndex)
2. Anclaje Visual de UI (FindUIElementTool)
3. Planificador y Heartbeat Daemon (AutonomousScheduler)
4. Orquestador de Subagentes (SubagentOrchestrator, DelegateSubagentTool)
5. Auditor de Salud y Auto-Reparación (SystemDoctor, SystemDoctorTool)
"""
import unittest
import tempfile
import shutil
import time
from pathlib import Path

from jev.core.semantic_memory import SemanticMemoryIndex
from jev.tools.ui_grounding import FindUIElementTool
from jev.core.scheduler import AutonomousScheduler, ScheduleTaskTool, ListScheduledTasksTool
from jev.core.subagents import SubagentOrchestrator, DelegateSubagentTool, SubagentRole
from jev.core.doctor import SystemDoctor, SystemDoctorTool
from jev.tools.base import ToolRegistry


class TestAdvancedAutonomy(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_semantic_memory_vector_search(self):
        index_file = self.temp_dir / "semantic_index.json"
        mem = SemanticMemoryIndex(storage_path=index_file)

        mem.add_entry(
            entry_id="sol_1",
            title="Arreglo de permisos en PowerShell",
            content="Para ejecutar scripts sin restricción usar Set-ExecutionPolicy RemoteSigned o -ExecutionPolicy Bypass.",
            metadata={"category": "powershell"}
        )
        mem.add_entry(
            entry_id="sol_2",
            title="Conexión SQLite FTS5",
            content="Crear tabla virtual con using fts5 para búsquedas ultrarrápidas de texto completo.",
            metadata={"category": "database"}
        )

        # Buscar por similitud semántica
        res = mem.search("ejecutar scripts powershell policy", top_k=1)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "sol_1")
        self.assertGreater(res[0]["similarity_score"], 0.1)

        # Verificar persistencia en disco
        self.assertTrue(index_file.exists())
        loaded_mem = SemanticMemoryIndex(storage_path=index_file)
        self.assertEqual(len(loaded_mem.documents), 2)

    def test_find_ui_element(self):
        finder = FindUIElementTool(workspace_dir=self.temp_dir)
        res = finder.execute(query="Cerrar ventana")
        self.assertTrue(res.success)
        self.assertIn("x", res.data)
        self.assertIn("y", res.data)

    def test_autonomous_scheduler(self):
        scheduler = AutonomousScheduler(check_interval=0.1)
        executed = []

        def sample_callback(job):
            executed.append(job.name)

        job_id = scheduler.add_job(
            name="test_periodic_cleanup",
            action_type="callback",
            payload="cleanup",
            delay_seconds=0.1,
            recurring=False,
            callback=sample_callback
        )
        self.assertIsInstance(job_id, str)

        # Esperar a que el daemon ejecute el job
        for _ in range(15):
            if "test_periodic_cleanup" in executed:
                break
            time.sleep(0.1)
        self.assertIn("test_periodic_cleanup", executed)

        # Herramientas del registro
        tool_schedule = ScheduleTaskTool(scheduler=scheduler)
        tool_list = ListScheduledTasksTool(scheduler=scheduler)

        res_sched = tool_schedule.execute(name="Reminder", delay_seconds=60, payload="Revisar servidor")
        self.assertTrue(res_sched.success)

        res_list = tool_list.execute()
        self.assertTrue(res_list.success)
        self.assertGreaterEqual(len(res_list.data["jobs"]), 1)

    def test_subagent_orchestrator(self):
        registry = ToolRegistry()
        orchestrator = SubagentOrchestrator(base_registry=registry)
        delegate_tool = DelegateSubagentTool(orchestrator=orchestrator)

        res = delegate_tool.execute(
            role=SubagentRole.RESEARCHER,
            subtask_prompt="Investigar compatibilidad de Python 3.11 en Windows"
        )
        self.assertTrue(res.success)
        self.assertIn("SUBAGENTE", res.output)
        self.assertEqual(res.data["role"], "researcher")

    def test_system_doctor(self):
        doctor = SystemDoctor(workspace_dir=self.temp_dir)
        tool = SystemDoctorTool(doctor=doctor)

        res = tool.execute(auto_heal=True)
        self.assertTrue(res.success)
        self.assertIn("INFORME MÉDICO", res.output)
        self.assertIn("disk_space", res.data["diagnostics"])
        self.assertIn("directories", res.data["diagnostics"])


if __name__ == "__main__":
    unittest.main()
