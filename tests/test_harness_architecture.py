"""
Suite de pruebas para la Arquitectura de Harness Recursivo (Harness² Integration).
Verifica:
1. Mutación y diffs del árbol de componentes c1..c8 (HarnessTree).
2. Biblioteca de experiencia persistente R con (cue, lesson, evidence) e INDEX.md.
3. Salvaguarda Answer-Free contra infiltración de rúbricas.
4. Ciclo Propose-Probe-Compose con ejecución de sondas locales.
5. Herramientas registradas en MMAEAutonomousAgent.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Añadir raíz
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.harness.tree import HarnessTree, HarnessComponent
from core.harness.library import ExperienceLibrary, assert_no_rubric_leak
from core.harness.recursion import RecursiveHarnessImprover, ProbeResult
from core.agent import MMAEAutonomousAgent


def test_harness_tree_diff_and_patch():
    base = HarnessTree.create_default()
    assert len(base.guardrails) >= 3
    assert "windows_automation" in base.skills

    # Aplicar parche (omitted is inherited)
    delta = {
        "guardrails": ["Nuevo guardrail de seguridad para red."],
        "scripts": {
            "test_script.py": "print('Hola desde harness')"
        }
    }
    patched = base.patch(delta)

    # Verificar herencia
    assert patched.system_prompt == base.system_prompt
    assert "windows_automation" in patched.skills
    assert "test_script.py" in patched.scripts
    assert any("red" in g for g in patched.guardrails)

    # Calcular diff
    diff = base.diff(patched)
    assert any("scripts" in item for item in diff["added"])
    assert any("guardrails" in item for item in diff["added"])


def test_harness_tree_disk_io():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        tree = HarnessTree.create_default()
        tree.scripts["limpiar.py"] = "import os; print('limpiando')"
        tree.write_to_dir(tmp_path)

        assert (tmp_path / "system_prompt.txt").is_file()
        assert (tmp_path / "guardrails.json").is_file()
        assert (tmp_path / "scripts" / "limpiar.py").is_file()

        loaded = HarnessTree.read_from_dir(tmp_path)
        assert loaded.system_prompt == tree.system_prompt
        assert "limpiar.py" in loaded.scripts


def test_experience_library_add_and_query():
    with tempfile.TemporaryDirectory() as tmp_dir:
        lib = ExperienceLibrary(domain="test_domain", root=Path(tmp_dir))
        assert lib.index_file.exists()

        tree = HarnessTree.create_default()
        exp_data = {
            "cue": "Error al ejecutar comandos PowerShell con comillas simples",
            "lesson": "Encapsular cadenas mediante bypass.py y usar Invoke-Expression",
            "evidence": "exit_code==0 verificado en Windows 11",
            "confidence": 0.98
        }

        entry_path = lib.add(
            task_id="tarea_powershell_01",
            harness=tree,
            experience=exp_data,
            why="Demostró inmunidad a corrupción de sintaxis CLI.",
            label="powershell_hardened"
        )
        assert entry_path.exists()
        assert (entry_path / "EXPERIENCE.md").exists()
        assert (entry_path / "harness").exists()

        # Verificar que INDEX.md se actualizó
        index_content = lib.index_file.read_text(encoding="utf-8")
        assert "tarea_powershell_01" in index_content
        assert "comillas simples" in index_content

        # Búsqueda por coincidencia de cue
        results = lib.find_relevant("powershell comillas corruptas", top_k=1)
        assert len(results) == 1
        assert results[0].task_id == "tarea_powershell_01"
        assert "bypass.py" in results[0].lesson

        # Inyección de prompt
        prompt_block = lib.export_prompt_injection("powershell comillas")
        assert "Biblioteca de Experiencias Previas" in prompt_block
        assert "bypass.py" in prompt_block


def test_answer_free_safeguard():
    caught = False
    try:
        assert_no_rubric_leak("Este script asume lo que the rubric exige")
    except ValueError:
        caught = True
    assert caught, "Debió bloquear la palabra prohibida de rúbrica"

    caught2 = False
    try:
        assert_no_rubric_leak({"justification": "cumple porque the grader expects exit 0"})
    except ValueError:
        caught2 = True
    assert caught2, "Debió bloquear 'the grader expects'"


def test_recursive_harness_improver_propose_probe_compose():
    improver = RecursiveHarnessImprover()
    base = HarnessTree.create_default()

    # Propose
    tree_a, tree_b, metadata = improver.propose(base, "Optimizar procesamiento de texto en archivos grandes")
    assert tree_a is not None
    assert tree_b is not None

    # Probe
    probe_a = improver.probe("candidate_a", tree_a, "procesamiento de texto")
    assert probe_a.success is True

    test_code = "import sys\nprint('Probe B exitosa')\nsys.exit(0)"
    probe_b = improver.probe("candidate_b", tree_b, "procesamiento de texto", test_script_code=test_code)
    assert probe_b.success is True
    assert "Probe B exitosa" in probe_b.output

    # Compose
    final_harness, comp_meta = improver.compose(base, probe_a, probe_b, "procesamiento de texto")
    assert final_harness is not None
    assert "experience" in comp_meta
    assert "cue" in comp_meta["experience"]
    assert "lesson" in comp_meta["experience"]


def test_agent_harness_skills_registration():
    agent = MMAEAutonomousAgent()
    assert "harness_inspect" in agent.registry.skills
    assert "experience_search" in agent.registry.skills
    assert "experience_record" in agent.registry.skills

    # Inspeccionar harness del agente
    h_data = agent.registry.skills["harness_inspect"]()
    assert "system_prompt" in h_data
    assert "guardrails" in h_data
    assert len(h_data["guardrails"]) >= 3


if __name__ == "__main__":
    print("Iniciando pruebas de arquitectura Harness²...")
    test_harness_tree_diff_and_patch()
    print("✅ test_harness_tree_diff_and_patch pasado.")
    test_harness_tree_disk_io()
    print("✅ test_harness_tree_disk_io pasado.")
    test_experience_library_add_and_query()
    print("✅ test_experience_library_add_and_query pasado.")
    test_answer_free_safeguard()
    print("✅ test_answer_free_safeguard pasado.")
    test_recursive_harness_improver_propose_probe_compose()
    print("✅ test_recursive_harness_improver_propose_probe_compose pasado.")
    test_agent_harness_skills_registration()
    print("✅ test_agent_harness_skills_registration pasado.")
    print("\n🎉 ¡TODAS LAS PRUEBAS DE HARNESS² PASARON EXITOSAMENTE (100%)!")
