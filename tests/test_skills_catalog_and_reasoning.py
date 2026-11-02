"""
Pruebas unitarias para el Catálogo de Habilidades (1,230+ skills),
Resolución de Conflictos, Motor de Razonamiento Profundo y Fine-Tuning con Soup.
"""
import json
from pathlib import Path
from core.skills.conflict_resolver import SkillConflictResolver
from core.skills.skill_rag import SkillRAG
from core.skills.catalog_indexer import SkillsCatalogIndexer
from core.reasoning.deep_thinker import DeepThinker
from core.fine_tuning.dataset_preparer import DatasetPreparer
from core.fine_tuning.soup_pipeline import SoupPipeline
from jev.tools.skill_finder import FindSkillTool
from jev.tools.soup_fine_tuner_tool import SoupFineTunerTool


def test_conflict_resolver_domain_assignment():
    """Verifica que las habilidades se clasifiquen en dominios y etiquetas correctas."""
    cat, tags, domain = SkillConflictResolver.assign_domain_and_tags(
        "tailwindlabs/tailwind-v4",
        "tailwind-v4",
        "Utility-first CSS framework for modern web development"
    )
    assert cat == "Frontend & UI"
    assert "tailwind" in tags
    assert domain == "styling_system"


def test_conflict_resolver_filters_contradictions():
    """Verifica que dos habilidades del mismo dominio exclusivo no se inyecten juntas."""
    candidates = [
        {
            "skill_id": "tailwindlabs/tailwind-v4",
            "tags": ["tailwind"],
            "conflict_domain": "styling_system",
            "rank_score": 1.0
        },
        {
            "skill_id": "twbs/bootstrap-v5",
            "tags": ["bootstrap"],
            "conflict_domain": "styling_system",
            "rank_score": 1.0
        }
    ]
    # Si el usuario menciona Tailwind en el contexto, Tailwind debe ganar y Bootstrap debe ser filtrado
    resolved = SkillConflictResolver.resolve_conflicts(
        candidates,
        context_hint="Necesito crear una interfaz moderna con Tailwind CSS",
        workspace_tech_stack=set()
    )
    assert len(resolved) == 1
    assert resolved[0]["skill_id"] == "tailwindlabs/tailwind-v4"


def test_skill_rag_search_and_prompt_formatting():
    """Verifica la búsqueda BM25 en la base de datos de 1,230+ skills."""
    rag = SkillRAG()
    results = rag.search("github workflow release", limit=3)
    assert len(results) > 0
    formatted = rag.format_skills_for_prompt(results)
    assert "HABILIDADES EXTERNAS RECUPERADAS" in formatted
    assert results[0]["skill_id"] in formatted


def test_find_skill_tool_execution():
    """Verifica que la herramienta FindSkillTool funcione correctamente como tool del agente."""
    tool = FindSkillTool()
    # 1. Búsqueda
    raw_res = tool.execute(query="playwright web testing", limit=2)
    res = json.loads(raw_res)
    assert res["status"] == "success"
    assert len(res["skills"]) > 0

    # 2. Inspección por skill_id
    raw_inspect = tool.execute(skill_id="anthropics/docx")
    inspect_res = json.loads(raw_inspect)
    assert inspect_res["status"] == "success"
    assert inspect_res["skill"]["owner"] == "anthropics"


def test_deep_thinker_strategy_deliberation():
    """Verifica la deliberación multi-hipótesis de DeepThinker."""
    thinker = DeepThinker()
    selected, candidates = thinker.deliberate_strategy("Montar un repositorio en GitHub y desplegar servidor")
    assert len(candidates) == 3
    assert selected.autonomy_score >= 0.90
    assert "Autónoma Defensiva" in selected.name


def test_deep_thinker_empirical_verification(tmp_path):
    """Verifica la comprobación física en disco de las herramientas."""
    thinker = DeepThinker(workspace_dir=tmp_path)

    # 1. Archivo inexistente
    fail_res = thinker.verify_tool_outcome(
        "write_file",
        {"path": str(tmp_path / "inexistente.txt")},
        "Archivo escrito"
    )
    assert not fail_res.is_valid

    # 2. Archivo real con contenido
    real_file = tmp_path / "valido.txt"
    real_file.write_text("print('hello')", encoding="utf-8")
    ok_res = thinker.verify_tool_outcome(
        "write_file",
        {"path": str(real_file)},
        "Archivo guardado"
    )
    assert ok_res.is_valid


def test_dataset_preparer_and_soup_config(tmp_path):
    """Verifica la preparación de dataset y generación de soup.yaml optimizado para QLoRA 4-bit."""
    preparer = DatasetPreparer(memory_dir=tmp_path)
    res = preparer.build_tool_calling_dataset(output_filename="test_dataset.jsonl")
    assert res["status"] == "success"
    assert res["total_samples"] >= 5

    pipeline = SoupPipeline(workspace_dir=tmp_path)
    cfg_path = pipeline.generate_soup_config(
        dataset_path=res["dataset_path"],
        base_model="Qwen/Qwen2.5-Coder-1.5B-Instruct",
        use_4bit_quant=True
    )
    assert Path(cfg_path).exists()
    cfg_text = Path(cfg_path).read_text(encoding="utf-8")
    assert "quantization: 4bit" in cfg_text
    assert "batch_size: auto" in cfg_text
    assert "format: tool-calling" in cfg_text


def test_soup_fine_tuner_tool():
    """Verifica que la herramienta SoupFineTunerTool responda a status y prepare_dataset."""
    tool = SoupFineTunerTool()
    status_raw = tool.execute(action="status")
    status = json.loads(status_raw)
    assert "soup_cli_installed" in status
    assert "workspace_dir" in status
