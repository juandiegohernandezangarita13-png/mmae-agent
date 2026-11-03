"""
Pruebas integrales de la nueva infraestructura MMAE:
1. Chronos y ExecutionTimer
2. Memoria Procedimental y Decaimiento Cognitivo
3. GoldfishCritic EGM
4. ScriptRunner CodeAct
"""
import sys
from pathlib import Path

# Añadir raíz
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.chronos import Chronos, ExecutionTimer
from core.memory.procedure_store import ProceduralMemoryManager
from core.goldfish_critic import GoldfishCritic
from core.script_runner import ScriptRunner


def test_chronos():
    print("--- Test Chronos ---")
    idle = Chronos.get_user_idle_seconds()
    print(f"User idle seconds: {idle:.2f}s")
    assert idle >= 0.0

    with ExecutionTimer(name="test_timer") as timer:
        total = sum(i * i for i in range(10000))
    print(f"Execution duration: {timer.duration_seconds:.6f}s, Success: {timer.success}")
    assert timer.success
    assert timer.duration_seconds > 0.0
    print("[PASS] Chronos & ExecutionTimer")


def test_memory_and_decay():
    print("\n--- Test Procedural Memory & Decay ---")
    pm = ProceduralMemoryManager()
    procs = pm.get_lowest_confidence_procedures(limit=3)
    print(f"Found {len(procs)} lowest confidence procedures.")
    if procs:
        p0 = procs[0]
        print(f"Proc ID={p0.id}, Cat={p0.category}, Confidence={p0.confidence_score}, LastVerified={p0.last_verified_at}")
        new_conf = pm.record_verification(p0.id, success=True)
        print(f"Updated confidence after verification: {new_conf}")
        assert new_conf > 0.0

    decayed = pm.apply_temporal_decay(decay_threshold_days=7.0)
    print(f"Decayed {decayed} procedures.")
    print("[PASS] Memory & Temporal Decay")


def test_goldfish_critic():
    print("\n--- Test Goldfish Critic ---")
    critic = GoldfishCritic()

    # Plan malo 1: Win32 sin timeout
    bad_plan_win32 = "1. Abrir app\n2. Usar win32gui para esperar ventana activa indefinidamente\n3. Enviar teclas"
    res1 = critic.audit_plan(bad_plan_win32)
    print("Bad plan Win32 approved?", res1.approved, "Blockers:", res1.blockers)
    assert not res1.approved
    assert any("timeout" in b.lower() for b in res1.blockers)

    # Plan bueno: Win32 con timeout explícito y bypass
    good_plan = "1. Inspeccionar objetivo con __LITERAL_TOKEN_0__\n2. Buscar ventana win32gui con timeout=10s\n3. Finalizar"
    res2 = critic.audit_plan(good_plan, literals=["C:\\test\\path.txt"])
    print("Good plan approved?", res2.approved, "Blockers:", res2.blockers)
    assert res2.approved
    print("[PASS] Goldfish Critic")


from core.evaluator import DeterministicOracle
from core.voice_announcer import VoiceAnnouncer
from core.curiosity_daemon import CuriosityDaemon


def test_script_runner():
    print("\n--- Test Script Runner ---")
    runner = ScriptRunner()
    code = """
import json
data = {"batch_inspected": 25, "active_services": ["mmae", "jev"], "status": "nominal"}
print(json.dumps(data))
"""
    result = runner.run_script(code)
    print("Script success:", result.success)
    print("Summary JSON:", result.summary_json)
    assert result.success
    assert result.summary_json.get("batch_inspected") == 25
    assert result.summary_json.get("status") == "nominal"
    print("[PASS] Script Runner")


def test_deterministic_oracle():
    print("\n--- Test Deterministic Oracle ---")
    oracle = DeterministicOracle()
    # 1. Exit code
    ec = oracle.verify_exit_code(0)
    assert ec["passed"]
    ec_bad = oracle.verify_exit_code(1)
    assert not ec_bad["passed"]

    # 2. File modification check
    test_file = ROOT / "workspace" / "_oracle_test.tmp"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    t_start = 1000.0  # past time
    test_file.write_text("ok", encoding="utf-8")
    fm = oracle.verify_file_modification(test_file, since_timestamp=t_start, min_bytes=1)
    assert fm["passed"]
    try:
        test_file.unlink()
    except Exception:
        pass

    # 3. Overall physical evaluation
    res = oracle.evaluate_physical_state(exit_code=0)
    assert res["success"]
    print("Oracle physical state verification passed:", res["verdict"])
    print("[PASS] Deterministic Oracle")


def test_voice_announcer():
    print("\n--- Test Voice Announcer (Non-blocking) ---")
    announcer = VoiceAnnouncer(enabled=True)
    # Debe encolar en < 5ms sin bloquear el hilo
    import time
    t0 = time.perf_counter()
    announcer.announce("Prueba de actuador de voz asíncrono MMAE.", priority="normal")
    dt = time.perf_counter() - t0
    print(f"Announcement enqueued in {dt*1000:.3f}ms")
    assert dt < 0.1  # Comprueba no-bloqueo
    print("[PASS] Voice Announcer")


def test_curiosity_daemon():
    print("\n--- Test Curiosity Daemon Cycle ---")
    # Umbral bajo para prueba manual inmediata
    daemon = CuriosityDaemon(idle_threshold_seconds=0.0)
    cycle_res = daemon.run_curiosity_cycle()
    print("Curiosity cycle executed:", cycle_res)
    assert cycle_res is not None
    assert "procedure_id" in cycle_res
    print("[PASS] Curiosity Daemon")


if __name__ == "__main__":
    test_chronos()
    test_memory_and_decay()
    test_goldfish_critic()
    test_script_runner()
    test_deterministic_oracle()
    test_voice_announcer()
    test_curiosity_daemon()
    print("\n=======================================================")
    print("TODAS LAS PRUEBAS 1 A 5 COMPLETADAS EXITOSAMENTE (100%)")
    print("=======================================================")
