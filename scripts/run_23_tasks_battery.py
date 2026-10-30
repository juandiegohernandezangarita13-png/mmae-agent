"""
Batería de Pruebas Extensas: 23 Tareas Críticas del Agente Autónomo MMAE / JEV.
Ejecuta y verifica de punta a punta:
1. Generación de Video por Código (MP4 / FFmpeg)
2. Modelado CAD 3D Robusto (CSG / STL / OBJ)
3. Escenas 3D para Viewport (Scene JSON)
4. Primitiva System-1 Jev Router: Choice
5. Primitiva System-1 Jev Router: Score
6. Primitiva System-1 Jev Router: Noul (Seguridad Binaria)
7. Ejecución de Código Python en Sandbox
8. Operaciones de Shell y Diagnóstico
9. Creación y Estructuración de Archivos
10. Lectura de Archivo e Integridad
11. Parcheo Quirúrgico de Código (PatchFileTool)
12. Inspección de Directorios (ListDirTool)
13. Memoria Procedimental SQLite: Inserción
14. Memoria Procedimental SQLite: Recuperación
15. Memoria Episódica Jerárquica
16. Búsqueda Web y Recuperación
17. Inspección de Repositorio GitHub
18. Planificador DAG y Descomposición
19. Control de Bucle y Detección de Ciclos
20. Persistencia y Checkpoints de Estado
21. Delegación a Subagentes Especializados
22. Generación de Artefactos Web Reactivos
23. Reflection Loop y Verificación de Efectos Secundarios
"""
import sys
import os
import json
import time
from pathlib import Path

# Configurar encoding UTF-8 en salida estándar de Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from jev.config import AgentConfig
from jev.core.agent import AgentCore
from jev_router import JevRouter, ChoiceResult, ScoreResult, NoulResult
from jev.tools.custom.skill_video_creator import AutoLaunchVideoTool
from jev.tools.custom.skill_cad_mesh import ParametricCadMeshTool
from jev.tools.viewport import Render3DSceneTool
from jev.tools.filesystem import ReadFileTool, WriteFileTool, PatchFileTool, ListDirTool
from jev.tools.code_runner import PythonRunnerTool, ShellCommandTool
from jev.tools.web import WebSearchTool, WebFetchTool
from jev.tools.github import GitHubRepoInspectTool
from jev.tools.skill_web_builder import WebBuilderTool
from jev.tools.base import ToolResult
from jev.core.memory import HierarchicalMemory
from jev.core.checkpoints import CheckpointManager
from jev.core.planner import DAGPlanner
from jev.core.verifier import ActionVerifier
from jev.core.subagents import SubagentOrchestrator, DelegateSubagentTool
from core.agent import MMAEAutonomousAgent


def run_battery():
    print("=" * 75)
    print("🚀 INICIANDO BATERÍA EXTENSA DE 23 TAREAS DEL AGENTE AUTÓNOMO MMAE/JEV")
    print("=" * 75)

    cfg = AgentConfig()
    ws_dir = cfg.workspace_dir
    ws_dir.mkdir(parents=True, exist_ok=True)

    agent = AgentCore(config=cfg)
    router = JevRouter()
    results = {}
    total_start = time.perf_counter()

    # -------------------------------------------------------------------------
    # Tarea 1: Generación de Video a Base de Código (MP4 / FFmpeg)
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 01/23] 🎬 Generación de Video a Base de Código...")
    try:
        video_tool = AutoLaunchVideoTool(workspace_dir=ws_dir)
        html_code = """<!DOCTYPE html>
        <html><head><title>JEV Autonomous Core</title></head>
        <body>
          <h1>Agente Autónomo JEV v2.6</h1>
          <p>Sistema inteligente de ejecución de código y toma de decisiones.</p>
          <ul>
            <li>Inferencia en tiempo real</li>
            <li>Renderizado de video procedural</li>
            <li>Seguridad System-1 TypeSafe AI</li>
          </ul>
        </body></html>"""
        v_res = video_tool.execute(
            action="create_launch_video",
            html_content=html_code,
            output_filename="bateria_video_launch.mp4",
            resolution="720p",
            fps=15
        )
        v_file = ws_dir / "bateria_video_launch.mp4"
        assert v_res.success, f"Fallo al generar video: {v_res.error}"
        assert v_file.exists(), f"El archivo {v_file} no existe en disco"
        assert v_file.stat().st_size > 5000, f"Tamaño de video anómalo: {v_file.stat().st_size} bytes"
        dur = time.perf_counter() - t_start
        print(f"  ✓ Video MP4 generado: {v_file.name} ({v_file.stat().st_size} bytes en {dur:.2f}s)")
        results["Tarea 01 - Video por Código"] = {"success": True, "duration_s": dur, "details": f"Archivo {v_file.name} ({v_file.stat().st_size} bytes)"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 01: {e}")
        results["Tarea 01 - Video por Código"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 2: Modelado CAD 3D Robusto (CSG / STL / OBJ)
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 02/23] ⚙️ Modelado CAD 3D Robusto...")
    try:
        cad_tool = ParametricCadMeshTool(workspace_dir=ws_dir)
        cad_res = cad_tool.execute(
            model_type="gear",
            name="bateria_engranaje",
            parameters={"teeth": 16, "pitch_diameter": 48.0, "thickness": 8.0, "bore_diameter": 10.0},
            export_formats=["stl", "obj"]
        )
        stl_file = ws_dir / "cad_models" / "bateria_engranaje.stl"
        assert cad_res.success, f"Fallo en CAD: {cad_res.error}"
        assert stl_file.exists(), f"El archivo STL {stl_file} no fue creado"
        assert stl_file.stat().st_size > 100, f"STL vacío o corrupto ({stl_file.stat().st_size} bytes)"
        dur = time.perf_counter() - t_start
        print(f"  ✓ Pieza CAD generada: {stl_file.name} ({stl_file.stat().st_size} bytes en {dur:.2f}s)")
        results["Tarea 02 - Modelado CAD 3D"] = {"success": True, "duration_s": dur, "details": f"STL {stl_file.name} ({stl_file.stat().st_size} bytes)"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 02: {e}")
        results["Tarea 02 - Modelado CAD 3D"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 3: Composición de Escena 3D Declarativa
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 03/23] 🌐 Composición de Escena 3D para Viewport...")
    try:
        scene_tool = Render3DSceneTool()
        scene_dict = {
            "title": "Escena de Prueba JEV",
            "elements": [
                {
                    "type": "mesh",
                    "geometry": {"type": "BoxGeometry", "parameters": {"width": 2, "height": 2, "depth": 2}},
                    "material": {"color": "#00f0ff"},
                    "position": [0, 0, 0]
                },
                {
                    "type": "mesh",
                    "geometry": {"type": "SphereGeometry", "parameters": {"radius": 1.5, "widthSegments": 16, "heightSegments": 16}},
                    "material": {"color": "#a855f7"},
                    "position": [3, 0, 0]
                }
            ]
        }
        sc_res = scene_tool.execute(scene=scene_dict, title="Escena Batería")
        assert sc_res.success, f"Fallo al componer escena 3D: {sc_res.error}"
        dur = time.perf_counter() - t_start
        print(f"  ✓ Escena 3D declarativa proyectada ({dur*1000:.1f}ms)")
        results["Tarea 03 - Escena 3D Viewport"] = {"success": True, "duration_s": dur, "details": "Escena Three.js válida"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 03: {e}")
        results["Tarea 03 - Escena 3D Viewport"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 4: System-1 Jev Router - Primitiva Choice
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 04/23] ⚡ System-1 Jev Router: Primitiva Choice...")
    try:
        opts = ["conversational_chat", "run_terminal", "read_file", "search_web"]
        ch_chat = router.choice("Hola JEV, ¿cómo estás?", opts)
        assert ch_chat.selected == "conversational_chat", f"Selección incorrecta: {ch_chat.selected}"
        assert ch_chat.latency_ms < 200.0, f"Latencia excedida: {ch_chat.latency_ms}ms"

        ch_cmd = router.choice("ejecutar comando de terminal para instalar dependencias", opts)
        assert ch_cmd.selected == "run_terminal", f"Selección incorrecta: {ch_cmd.selected}"
        dur = time.perf_counter() - t_start
        print(f"  ✓ Choice evaluado correctamente (Latencia: {ch_chat.latency_ms:.2f}ms)")
        results["Tarea 04 - Jev Choice"] = {"success": True, "duration_s": dur, "details": f"Chat->'{ch_chat.selected}', Cmd->'{ch_cmd.selected}'"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 04: {e}")
        results["Tarea 04 - Jev Choice"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 5: System-1 Jev Router - Primitiva Score
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 05/23] ⚡ System-1 Jev Router: Primitiva Score...")
    try:
        sc_low = router.score("Hola", metric="complexity")
        sc_high = router.score("Crear microservicio, configurar docker, migrar base de datos y publicar API", metric="complexity")
        assert sc_low.score < sc_high.score, f"Inconsistencia en scores: low={sc_low.score}, high={sc_high.score}"
        assert sc_low.latency_ms < 200.0
        dur = time.perf_counter() - t_start
        print(f"  ✓ Score evaluado (Baja: {sc_low.score:.2f}, Alta: {sc_high.score:.2f})")
        results["Tarea 05 - Jev Score"] = {"success": True, "duration_s": dur, "details": f"Low={sc_low.score:.2f}, High={sc_high.score:.2f}"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 05: {e}")
        results["Tarea 05 - Jev Score"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 6: System-1 Jev Router - Primitiva Noul (Seguridad Binaria)
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 06/23] 🛡️ System-1 Jev Router: Primitiva Noul...")
    try:
        noul_blocked = router.noul("rm -rf /")
        assert not noul_blocked.allowed, "Noul debió bloquear 'rm -rf /'"
        assert noul_blocked.violation_reason is not None

        noul_allowed = router.noul("git status")
        assert noul_allowed.allowed, "Noul debió permitir 'git status'"
        dur = time.perf_counter() - t_start
        print(f"  ✓ Noul bloqueó comando malicioso en {noul_blocked.latency_ms:.2f}ms y permitió comando seguro")
        results["Tarea 06 - Jev Noul"] = {"success": True, "duration_s": dur, "details": f"Bloqueado: '{noul_blocked.violation_reason}'"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 06: {e}")
        results["Tarea 06 - Jev Noul"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 7: Ejecución de Código Python en Sandbox
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 07/23] 🐍 Ejecución de Código Python en Sandbox...")
    try:
        py_tool = PythonRunnerTool(workspace_dir=ws_dir)
        py_code = """
import math
primes = [n for n in range(2, 50) if all(n % d != 0 for d in range(2, int(math.isqrt(n)) + 1))]
print(f"PRIMES_COUNT:{len(primes)}")
print(f"SUM:{sum(primes)}")
"""
        py_res = py_tool.execute(code=py_code)
        assert py_res.success, f"Error en Python runner: {py_res.error}"
        assert "PRIMES_COUNT:15" in py_res.output
        assert "SUM:328" in py_res.output
        dur = time.perf_counter() - t_start
        print(f"  ✓ Python sandbox ejecutado con éxito ({dur*1000:.1f}ms)")
        results["Tarea 07 - Python Sandbox"] = {"success": True, "duration_s": dur, "details": "Cálculo de números primos correcto"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 07: {e}")
        results["Tarea 07 - Python Sandbox"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 8: Operaciones de Shell / Diagnóstico de Sistema
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 08/23] 💻 Operaciones de Shell y Diagnóstico...")
    try:
        sh_tool = ShellCommandTool(workspace_dir=ws_dir)
        sh_res = sh_tool.execute(command="powershell -Command \"Get-Date -Format yyyy-MM-dd\"")
        assert sh_res.success, f"Error en shell: {sh_res.error}"
        assert len(sh_res.output.strip()) >= 10
        dur = time.perf_counter() - t_start
        print(f"  ✓ Shell ejecutó comando de sistema")
        results["Tarea 08 - Shell Diagnostics"] = {"success": True, "duration_s": dur, "details": "Diagnóstico de fecha completado"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 08: {e}")
        results["Tarea 08 - Shell Diagnostics"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 9: Creación y Estructuración de Archivos
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 09/23] 📝 Creación de Archivos...")
    try:
        wf_tool = WriteFileTool(workspace_dir=ws_dir)
        test_py = ws_dir / "bateria_modulo.py"
        content = "def calcular_potencia(base, exp):\n    return base ** exp\n"
        w_res = wf_tool.execute(path="bateria_modulo.py", content=content)
        assert w_res.success, f"Error escribiendo archivo: {w_res.error}"
        assert test_py.exists()
        dur = time.perf_counter() - t_start
        print(f"  ✓ Archivo creado: {test_py.name}")
        results["Tarea 09 - Creación de Archivos"] = {"success": True, "duration_s": dur, "details": f"Creado {test_py.name}"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 09: {e}")
        results["Tarea 09 - Creación de Archivos"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 10: Lectura y Verificación de Integridad de Archivo
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 10/23] 📖 Lectura de Archivo e Integridad...")
    try:
        rf_tool = ReadFileTool(workspace_dir=ws_dir)
        r_res = rf_tool.execute(path="bateria_modulo.py")
        assert r_res.success, f"Error leyendo archivo: {r_res.error}"
        assert "def calcular_potencia" in r_res.output
        dur = time.perf_counter() - t_start
        print(f"  ✓ Archivo leído e integridad confirmada")
        results["Tarea 10 - Lectura de Archivo"] = {"success": True, "duration_s": dur, "details": "Contenido íntegro"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 10: {e}")
        results["Tarea 10 - Lectura de Archivo"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 11: Parcheo Quirúrgico de Archivo
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 11/23] 🩹 Parcheo Quirúrgico de Código...")
    try:
        pf_tool = PatchFileTool(workspace_dir=ws_dir)
        old_str = "    return base ** exp\n"
        new_str = "    # Parcheado optimizado\n    return pow(base, exp)\n"
        p_res = pf_tool.execute(path="bateria_modulo.py", target_content=old_str, replacement_content=new_str)
        assert p_res.success, f"Error parcheando archivo: {p_res.error}"
        with open(ws_dir / "bateria_modulo.py", "r", encoding="utf-8") as f:
            patched = f.read()
        assert "pow(base, exp)" in patched
        dur = time.perf_counter() - t_start
        print(f"  ✓ Archivo parcheado con éxito")
        results["Tarea 11 - Parcheo Quirúrgico"] = {"success": True, "duration_s": dur, "details": "Reemplazo exacto aplicado"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 11: {e}")
        results["Tarea 11 - Parcheo Quirúrgico"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 12: Inspección de Directorios y Árbol de Trabajo
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 12/23] 📂 Inspección de Directorios...")
    try:
        ld_tool = ListDirTool(workspace_dir=ws_dir)
        ld_res = ld_tool.execute(path=".")
        assert ld_res.success, f"Error listando directorio: {ld_res.error}"
        assert "bateria_modulo.py" in ld_res.output
        dur = time.perf_counter() - t_start
        print(f"  ✓ Directorio listado correctamente")
        results["Tarea 12 - Listado de Directorios"] = {"success": True, "duration_s": dur, "details": "Directorio analizado"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 12: {e}")
        results["Tarea 12 - Listado de Directorios"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 13: Memoria Procedimental SQLite - Inserción
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 13/23] 💾 Memoria Procedimental SQLite (Inserción)...")
    try:
        mem = HierarchicalMemory(memory_dir=cfg.memory_dir)
        mem.save_solution(
            category="ffmpeg_video",
            trigger_keywords="video ffmpeg renderizar mp4 codec",
            problem_description="Optimizar renderizado de video en ffmpeg",
            solution_summary="Usar códec libx264 con -pix_fmt yuv420p y flags faststart",
            working_snippet="ffmpeg -y -framerate 30 -i frame_%05d.png -c:v libx264 -pix_fmt yuv420p video.mp4"
        )
        dur = time.perf_counter() - t_start
        print(f"  ✓ Solución procedimental persistida en SQLite")
        results["Tarea 13 - Memoria SQLite Inserción"] = {"success": True, "duration_s": dur, "details": "Registro procedimental guardado"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 13: {e}")
        results["Tarea 13 - Memoria SQLite Inserción"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 14: Memoria Procedimental SQLite - Recuperación
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 14/23] 🔍 Memoria Procedimental SQLite (Recuperación)...")
    try:
        mem = HierarchicalMemory(memory_dir=cfg.memory_dir)
        proc_ctx = mem.get_procedural_context_for_goal("video ffmpeg")
        assert len(proc_ctx) > 0, "No se recuperó contexto procedimental"
        assert "libx264" in proc_ctx or "ffmpeg" in proc_ctx.lower()
        dur = time.perf_counter() - t_start
        print(f"  ✓ Contexto procedimental recuperado con éxito")
        results["Tarea 14 - Memoria SQLite Recuperación"] = {"success": True, "duration_s": dur, "details": "Snippet recuperado"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 14: {e}")
        results["Tarea 14 - Memoria SQLite Recuperación"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 15: Memoria Episódica Jerárquica
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 15/23] 🧠 Memoria Episódica Jerárquica...")
    try:
        mem = HierarchicalMemory(memory_dir=cfg.memory_dir)
        mem.record_episode(
            task="ejecucion de prueba de bateria",
            success=True,
            steps_count=5,
            tools_used=["skill_video_creator", "skill_cad_mesh"],
            summary="Batería de pruebas extensas ejecutada sin fallos"
        )
        assert mem.episodes_file.exists() and mem.episodes_file.stat().st_size > 0
        dur = time.perf_counter() - t_start
        print(f"  ✓ Episodio persistido en memoria jerárquica ({mem.episodes_file.name})")
        results["Tarea 15 - Memoria Episódica"] = {"success": True, "duration_s": dur, "details": "Episodio registrado en JSONL"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 15: {e}")
        results["Tarea 15 - Memoria Episódica"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 16: Búsqueda Web y Extracción de Contenido
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 16/23] 🌐 Búsqueda Web y Recuperación...")
    try:
        ws_tool = WebSearchTool()
        s_res = ws_tool.execute(query="python programming language", max_results=3)
        assert s_res.success, f"Error en búsqueda web: {s_res.error}"
        assert len(s_res.output) > 20
        dur = time.perf_counter() - t_start
        print(f"  ✓ Búsqueda web ejecutada ({len(s_res.output)} chars devueltos)")
        results["Tarea 16 - Búsqueda Web"] = {"success": True, "duration_s": dur, "details": f"{len(s_res.output)} bytes recibidos"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 16: {e}")
        results["Tarea 16 - Búsqueda Web"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 17: Inspección de Repositorio GitHub
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 17/23] 🐙 Inspección de Repositorio GitHub...")
    try:
        gh_tool = GitHubRepoInspectTool()
        gh_res = gh_tool.execute(repo_full_name="psf/requests")
        assert gh_res.success, f"Error en GitHub tool: {gh_res.error}"
        assert "requests" in gh_res.output.lower()
        dur = time.perf_counter() - t_start
        print(f"  ✓ Repositorio GitHub inspeccionado correctamente")
        results["Tarea 17 - GitHub Inspect"] = {"success": True, "duration_s": dur, "details": "Repositorio psf/requests verificado"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 17: {e}")
        results["Tarea 17 - GitHub Inspect"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 18: Planificador DAG y Descomposición de Tareas
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 18/23] 📋 Planificador DAG y Descomposición...")
    try:
        planner = DAGPlanner(llm_client=agent.llm)
        plan = planner.create_plan("Diseñar e implementar una API REST con base de datos SQLite y tests")
        assert len(plan.tasks) >= 2, f"Plan DAG incompleto: {len(plan.tasks)} tareas"
        dur = time.perf_counter() - t_start
        print(f"  ✓ Plan DAG generado con {len(plan.tasks)} micro-tareas secuenciales")
        results["Tarea 18 - Planificador DAG"] = {"success": True, "duration_s": dur, "details": f"{len(plan.tasks)} subtareas estructuradas"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 18: {e}")
        results["Tarea 18 - Planificador DAG"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 19: Control de Bucle y Detección de Ciclos
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 19/23] 🔄 Control de Bucle y Detección de Ciclos...")
    try:
        mem = HierarchicalMemory(memory_dir=cfg.memory_dir)
        sess = f"test_loop_{int(time.time())}"
        mem.record_step(sess, 1, "read_file", {"path": "bateria_modulo.py"}, success=True)
        is_dup = mem.is_step_duplicated(sess, "read_file", {"path": "bateria_modulo.py"})
        assert is_dup, "Debería detectar el paso como duplicado"
        dur = time.perf_counter() - t_start
        print(f"  ✓ Detector de ciclos y pasos duplicados operativo")
        results["Tarea 19 - Detección de Ciclos"] = {"success": True, "duration_s": dur, "details": "Deduplicación confirmada"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 19: {e}")
        results["Tarea 19 - Detección de Ciclos"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 20: Persistencia y Checkpoints de Estado
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 20/23] 💾 Persistencia y Checkpoints de Estado...")
    try:
        chk = CheckpointManager(checkpoints_dir=cfg.memory_dir / "checkpoints")
        tid = f"test_task_{int(time.time())}"
        chk.save_checkpoint(
            task_id=tid,
            goal="Probar checkpointing y restauración atómica",
            plan_dict={"tasks": [{"id": 1, "title": "Subtarea A"}]},
            completed_step_count=1,
            messages=[{"role": "user", "content": "iniciar prueba"}]
        )
        loaded = chk.load_checkpoint(tid)
        assert loaded is not None
        assert loaded["task_id"] == tid
        dur = time.perf_counter() - t_start
        print(f"  ✓ Checkpoint persistido y restaurado con éxito")
        results["Tarea 20 - Checkpoint & Restore"] = {"success": True, "duration_s": dur, "details": f"Checkpoint {tid} verificado"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 20: {e}")
        results["Tarea 20 - Checkpoint & Restore"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 21: Delegación a Subagentes Especializados
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 21/23] 🤖 Delegación y Enjambre de Subagentes...")
    try:
        orch = SubagentOrchestrator(base_registry=agent.registry)
        del_tool = DelegateSubagentTool(orchestrator=orch)
        del_res = del_tool.execute(
            role="coder",
            subtask_prompt="Calcular la suma de enteros de 1 a 10"
        )
        assert del_res.success, f"Error en delegación a subagente: {del_res.error}"
        dur = time.perf_counter() - t_start
        print(f"  ✓ Subagente 'coder' ejecutó y retornó resultado")
        results["Tarea 21 - Delegación Subagentes"] = {"success": True, "duration_s": dur, "details": "Subagente completó tarea"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 21: {e}")
        results["Tarea 21 - Delegación Subagentes"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 22: Generación de Artefactos Web Reactivos
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 22/23] 🎨 Generación de Artefactos Web Reactivos...")
    try:
        web_tool = WebBuilderTool(workspace_dir=ws_dir)
        w_res = web_tool.execute(
            template_type="dashboard",
            title="Panel de Control Autónomo",
            output_filename="bateria_dashboard.html"
        )
        dash_html = ws_dir / "web_artifacts" / "bateria_dashboard.html"
        assert w_res.success, f"Error en WebBuilderTool: {w_res.error}"
        assert dash_html.exists(), f"El archivo {dash_html} no fue creado"
        assert dash_html.stat().st_size > 300, f"Dashboard web incompleto ({dash_html.stat().st_size} bytes)"
        dur = time.perf_counter() - t_start
        print(f"  ✓ Dashboard Web Reactivo generado: {dash_html.name} ({dash_html.stat().st_size} bytes)")
        results["Tarea 22 - Web Builder"] = {"success": True, "duration_s": dur, "details": f"Dashboard {dash_html.name} ({dash_html.stat().st_size} bytes)"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 22: {e}")
        results["Tarea 22 - Web Builder"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Tarea 23: Reflection Loop y Verificación de Efectos Secundarios
    # -------------------------------------------------------------------------
    t_start = time.perf_counter()
    print("\n[Tarea 23/23] 🔍 Reflection Loop y Verificación de Efectos Secundarios...")
    try:
        verifier = ActionVerifier(workspace_dir=ws_dir)
        mock_result = ToolResult(success=True, output="Archivo guardado")
        ver_action = verifier.verify_action("write_file", {"path": "bateria_modulo.py"}, mock_result)
        assert ver_action.passed, f"Reflection falló en write_file: {ver_action.reason}"

        # Comprobar existencia física de video MP4 y modelo CAD STL
        v_file = ws_dir / "bateria_video_launch.mp4"
        stl_file = ws_dir / "cad_models" / "bateria_engranaje.stl"
        assert v_file.exists() and v_file.stat().st_size > 5000, "El video de prueba no es válido"
        assert stl_file.exists() and stl_file.stat().st_size > 100, "La pieza CAD no es válida"

        dur = time.perf_counter() - t_start
        print(f"  ✓ Reflection Loop verificó objetivamente que los artefactos generados existen y son válidos")
        results["Tarea 23 - Reflection Verifier"] = {"success": True, "duration_s": dur, "details": "Verificación física de disco exitosa"}
    except Exception as e:
        print(f"  ❌ Fallo en Tarea 23: {e}")
        results["Tarea 23 - Reflection Verifier"] = {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # RESUMEN GENERAL Y AUDITORÍA DE RESULTADOS
    # -------------------------------------------------------------------------
    total_time = time.perf_counter() - total_start
    passed = sum(1 for r in results.values() if r.get("success"))
    failed = len(results) - passed

    print("\n" + "=" * 75)
    print("📊 RESUMEN FINAL DE LA BATERÍA EXTENSA (23 TAREAS)")
    print("=" * 75)
    for name, data in results.items():
        status = "✅ PASS" if data.get("success") else "❌ FAIL"
        dur_str = f"({data.get('duration_s', 0):.2f}s)" if "duration_s" in data else ""
        details = data.get("details") or data.get("error") or ""
        print(f"{status} | {name:<38} {dur_str:<9} | {details}")

    print("-" * 75)
    print(f"TOTAL: {len(results)} Tareas | APROBADAS: {passed} | FALLIDAS: {failed} | TIEMPO TOTAL: {total_time:.2f}s")
    print("=" * 75)

    # Guardar reporte estructurado en disco
    report_file = BASE_DIR / "bateria_23_tareas_reporte.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tasks": len(results),
            "passed": passed,
            "failed": failed,
            "total_duration_seconds": round(total_time, 2),
            "tasks": results
        }, f, indent=2, ensure_ascii=False)
    print(f"\n📄 Reporte persistido en: {report_file}")

    return passed == len(results)


if __name__ == "__main__":
    success = run_battery()
    sys.exit(0 if success else 1)
