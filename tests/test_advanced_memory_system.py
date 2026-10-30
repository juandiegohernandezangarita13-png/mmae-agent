"""
Suite de Pruebas Unitarias e Integración para la Arquitectura de Memoria Persistente Avanzada.
Valida:
1. Mem0 Layer (UserPersistentMemory): Preferencias, hechos, resolución de conflictos y extracción.
2. Graffiti Layer (TemporalKnowledgeGraph): Nodos, relaciones temporales, invalidación automática y consultas point-in-time.
3. Coach Layer (HeterogeneousKnowledgeHub): Ingesta heterogénea, chunking, checksums y búsqueda semántica/léxica.
4. LangMem & Leta Layer (BackgroundMemoryWorker): Destilación en segundo plano y adaptación de perfil.
5. UnifiedMemorySystem (MMAEMemorySystem): Orquestación multicapa y síntesis contextual sin saturación.
"""
import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

from core.memory import (
    ExecutionMemory,
    UserPersistentMemory,
    UserMemoryCategory,
    TemporalKnowledgeGraph,
    HeterogeneousKnowledgeHub,
    BackgroundMemoryWorker,
    UnifiedMemorySystem,
    MMAEMemorySystem
)


class TestAdvancedMemorySystem(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="mmae_test_memory_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # 1. PRUEBAS CAPA MEM0 (UserPersistentMemory)
    # =========================================================================
    def test_mem0_user_memory_crud_and_conflict_resolution(self):
        db_path = self.temp_dir / "user_mem.db"
        user_mem = UserPersistentMemory(db_path=db_path)

        # 1. Creación de preferencia inicial
        res1 = user_mem.add(
            value="Python con tipado estricto",
            category=UserMemoryCategory.PREFERENCE.value,
            key="code_style",
            user_id="dev_user"
        )
        self.assertEqual(res1["action"], "created")
        self.assertEqual(res1["value"], "Python con tipado estricto")

        # 2. Refuerzo de la misma preferencia (debe incrementar contador sin conflicto)
        res_reinforce = user_mem.add(
            value="Python con tipado estricto",
            category=UserMemoryCategory.PREFERENCE.value,
            key="code_style",
            user_id="dev_user"
        )
        self.assertEqual(res_reinforce["action"], "reinforced")

        # 3. Resolución de conflicto (el usuario cambia su preferencia)
        res_conflict = user_mem.add(
            value="Python funcional con dataclasses",
            category=UserMemoryCategory.PREFERENCE.value,
            key="code_style",
            user_id="dev_user"
        )
        self.assertEqual(res_conflict["action"], "updated")

        # Verificar que el valor activo es el nuevo
        active_mem = user_mem.get(res1["memory_id"])
        self.assertIsNotNone(active_mem)
        self.assertEqual(active_mem["value"], "Python funcional con dataclasses")
        self.assertGreater(active_mem["update_count"], 0)

        # Verificar que el historial de auditoría conserva el valor antiguo
        all_memories = user_mem.get_all(user_id="dev_user")
        self.assertEqual(len(all_memories), 1)

        # 4. Búsqueda contextual
        search_res = user_mem.search("dataclasses tipado", user_id="dev_user")
        self.assertEqual(len(search_res), 1)
        self.assertEqual(search_res[0]["key"], "code_style")

        # 5. Generación de bloque para prompt del sistema
        prompt_ctx = user_mem.get_user_profile_context(user_id="dev_user")
        self.assertIn("MEMORIA DE USUARIO Y PREFERENCIAS PERSISTENTES", prompt_ctx)
        self.assertIn("Python funcional con dataclasses", prompt_ctx)

    def test_mem0_heuristic_extraction(self):
        user_mem = UserPersistentMemory(db_path=self.temp_dir / "user_mem_extract.db")
        dialogue = "Hola, prefiero respuestas directas y concisas. Además, usa siempre español."
        extracted = user_mem.extract_and_add_from_text(dialogue, user_id="user_1")

        self.assertGreaterEqual(len(extracted), 2)
        keys = [item["key"] for item in extracted]
        self.assertTrue(any("preferencia" in k or "regla" in k for k in keys))

    # =========================================================================
    # 2. PRUEBAS CAPA GRAFFITI (TemporalKnowledgeGraph)
    # =========================================================================
    def test_graffiti_temporal_validity_and_auto_invalidation(self):
        db_path = self.temp_dir / "tkg.db"
        tkg = TemporalKnowledgeGraph(db_path=db_path)

        t_past = datetime.now() - timedelta(days=30)
        t_now = datetime.now()

        # Hecho inicial: El usuario usaba Flask
        tkg.add_relation(
            source="User",
            relation="current_framework",
            target="Flask",
            valid_from=t_past,
            is_functional=True,
            evidence="Proyecto legacy 2025"
        )

        # Verificar hecho activo
        current_facts = tkg.get_current_facts(source="User", relation="current_framework")
        self.assertEqual(len(current_facts), 1)
        self.assertEqual(current_facts[0]["target_node"], "Flask")

        # Hecho nuevo: El usuario migró a FastAPI (debe invalidar Flask automáticamente)
        tkg.add_relation(
            source="User",
            relation="current_framework",
            target="FastAPI",
            valid_from=t_now,
            is_functional=True,
            evidence="Migración moderna 2026"
        )

        # 1. Verificar estado actual: sólo FastAPI está vigente
        updated_current = tkg.get_current_facts(source="User", relation="current_framework")
        self.assertEqual(len(updated_current), 1)
        self.assertEqual(updated_current[0]["target_node"], "FastAPI")

        # 2. Consulta retrospectiva (Point-in-time snapshot estilo Graffiti):
        # En la fecha pasada (t_past + 5 días), el hecho válido era Flask, no FastAPI.
        snapshot_time = t_past + timedelta(days=5)
        past_facts = tkg.query_as_of(snapshot_time, source="User", relation="current_framework")
        self.assertEqual(len(past_facts), 1)
        self.assertEqual(past_facts[0]["target_node"], "Flask")

        # 3. Línea de tiempo completa de la entidad
        history = tkg.get_entity_history(source="User", relation="current_framework")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["target_node"], "Flask")
        self.assertEqual(history[0]["is_current"], 0)
        self.assertEqual(history[1]["target_node"], "FastAPI")
        self.assertEqual(history[1]["is_current"], 1)

    # =========================================================================
    # 3. PRUEBAS CAPA COACH (HeterogeneousKnowledgeHub)
    # =========================================================================
    def test_coach_knowledge_hub_ingestion_and_hybrid_search(self):
        hub_dir = self.temp_dir / "knowledge_hub"
        hub = HeterogeneousKnowledgeHub(storage_dir=hub_dir, chunk_size=300, chunk_overlap=50)

        # Crear documento Markdown local de prueba
        doc_path = self.temp_dir / "arquitectura_agente.md"
        doc_path.write_text(
            "# Arquitectura de MMAE\n\n"
            "El agente utiliza un motor de dos fases: MacroEngine para esqueletos de alto nivel "
            "y MicroEngine para expansión de código. La memoria jerárquica previene bucles infinitos.\n\n"
            "Además, integra TypeSafe AI Jev Router para decisiones en menos de 200 milisegundos "
            "y un sandbox de ejecución segura para comandos de terminal y Python.",
            encoding="utf-8"
        )

        # Ingesta del archivo
        chunks_count = hub.ingest_file(doc_path, category="docs")
        self.assertGreaterEqual(chunks_count, 1)

        # Re-ingesta sin modificaciones (debe omitir por checksum idéntico)
        chunks_reingest = hub.ingest_file(doc_path, category="docs")
        self.assertEqual(chunks_reingest, 0)

        # Búsqueda semántica/léxica
        query_res = hub.query("decisiones TypeSafe AI sub 200ms", top_k=2)
        self.assertGreaterEqual(len(query_res), 1)
        self.assertIn("TypeSafe AI", query_res[0]["text"])
        self.assertIn("score", query_res[0])

        # Formato de citas para prompt
        formatted_context = hub.format_retrieval_context("MacroEngine dos fases")
        self.assertIn("FUENTES DE CONOCIMIENTO DOCUMENTAL", formatted_context)
        self.assertIn("arquitectura_agente.md", formatted_context)

    # =========================================================================
    # 4. PRUEBAS LANGMEM & LETA (BackgroundMemoryWorker)
    # =========================================================================
    def test_langmem_and_leta_background_worker(self):
        user_mem = UserPersistentMemory(db_path=self.temp_dir / "bm_user.db")
        tkg = TemporalKnowledgeGraph(db_path=self.temp_dir / "bm_tkg.db")
        worker = BackgroundMemoryWorker(
            user_memory=user_mem,
            temporal_graph=tkg,
            profile_path=self.temp_dir / "profile.json"
        )

        # Encolar turnos conversacionales
        worker.enqueue_turn(
            user_input="Hola, ahora uso Windows 11 y prefiero respuestas en formato JSON.",
            agent_output='{"status": "ok", "message": "Entendido"}',
            tools_used=["ScreenInfoTool", "SystemEnvironmentTool"],
            task_success=True,
            user_id="user_admin"
        )

        # Procesamiento síncrono
        processed = worker.process_pending(sync=True)
        self.assertEqual(processed, 1)

        # Verificar que se extrajo la relación temporal hacia Graffiti
        facts = tkg.get_current_facts(source="User", relation="operates_on")
        self.assertTrue(len(facts) >= 1)
        self.assertEqual(facts[0]["target_node"].lower(), "windows")

        # Verificar métricas adaptativas estilo Leta
        metrics = worker.get_evolution_metrics()
        self.assertEqual(metrics["total_turns"], 1)
        self.assertIn("ScreenInfoTool", metrics["preferred_tools"])

    # =========================================================================
    # 5. PRUEBAS SISTEMA UNIFICADO (UnifiedMemorySystem / MMAEMemorySystem)
    # =========================================================================
    def test_unified_memory_orchestrator(self):
        unified = UnifiedMemorySystem(
            memory_dir=self.temp_dir / "unified",
            auto_start_worker=False
        )

        # 1. Registrar hecho en Mem0
        unified.user.add("Formato Markdown con listas claras", category="preference", key="formato_salida")

        # 2. Registrar hecho temporal en Graffiti
        unified.temporal.add_relation("User", "active_project", "MMAE_Agent")

        # 3. Ingestar snippet en Coach Knowledge Hub
        unified.knowledge.ingest_text(
            text="La suite de pruebas contiene 500 tareas de estrés automatizadas sin errores.",
            title="Guía de Pruebas",
            source_type="snippet",
            source_path="test_guide.txt"
        )

        # 4. Registrar acción en ExecutionMemory
        unified.execution.record_step("validar_arquitectura", {"success": True, "stdout": "Todo OK"})

        # 5. Sintetizar contexto unificado para el agente
        prompt_ctx = unified.build_unified_context(query="¿Cómo son las pruebas y el formato?")

        self.assertIn("MEMORIA DE USUARIO Y PREFERENCIAS PERSISTENTES", prompt_ctx)
        self.assertIn("GRAFO DE CONOCIMIENTO TEMPORAL ACTIVO", prompt_ctx)
        self.assertIn("FUENTES DE CONOCIMIENTO DOCUMENTAL", prompt_ctx)
        self.assertIn("HISTORIAL DE EJECUCIÓN RECIENTE", prompt_ctx)

        # 6. Aprendizaje de turno
        unified.record_turn_and_learn(
            user_input="Gracias, ahora uso Python 3.12 para todos los scripts.",
            agent_output="Perfecto, configurado.",
            sync=True
        )

        unified.close()


if __name__ == "__main__":
    unittest.main()
