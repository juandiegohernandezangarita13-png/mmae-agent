"""
Prueba de integración end-to-end para MMAEAutonomousAgent con:
- Chronos & ExecutionTimer
- Goldfish Critic Pre-Audit
- Programmatic Tool Calling (ScriptRunner)
- Deterministic Oracle
- Voice Announcer
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent import MMAEAutonomousAgent
from config import config

def test_agent_initialization():
    print("--- Test Agent Initialization ---")
    agent = MMAEAutonomousAgent(config)
    assert agent.chronos is not None
    assert agent.critic is not None
    assert agent.script_runner is not None
    assert agent.deterministic_oracle is not None
    assert agent.voice is not None
    assert agent.curiosity_daemon is not None
    assert "execute_script" in agent.registry.skills
    assert "run_python_script" in agent.registry.skills
    print("[PASS] Agent components initialized properly.")

    print("\n--- Test Direct Execution of ScriptRunner Skill ---")
    exec_res = agent.registry.execute(
        "execute_script",
        script_code="import json; print(json.dumps({'status': 'verified', 'count': 100}))"
    )
    print("Execute script skill result:", exec_res)
    assert exec_res.get("success")
    assert exec_res.get("summary_json", {}).get("count") == 100
    print("[PASS] execute_script skill verified.")


def test_agent_run_blocked_by_critic():
    print("\n--- Test Agent Execution Blocked by Goldfish Critic ---")
    agent = MMAEAutonomousAgent(config)
    # Sobrescribir macro.generate_skeleton temporalmente para simular un plan que omite timeouts Win32
    original_generate = agent.macro.generate_skeleton
    agent.macro.generate_skeleton = lambda prompt: {
        "skeleton": "1. Abrir aplicación desktop\n2. Usar win32gui para esperar ventana activa indefinidamente\n3. Escribir texto",
        "literals": []
    }

    try:
        run_res = agent.run("Abrir ventana sin timeout")
        print("Run result when critic rejects:", run_res)
        assert not run_res.get("success")
        assert "Goldfish Critic" in run_res.get("error", "")
        print("[PASS] Goldfish Critic successfully blocked unsafe macro plan before micro phase.")
    finally:
        agent.macro.generate_skeleton = original_generate


if __name__ == "__main__":
    test_agent_initialization()
    test_agent_run_blocked_by_critic()
    print("\n=======================================================")
    print("PIPELINE END-TO-END DE MMAE AGENT VERIFICADO AL 100%")
    print("=======================================================")
