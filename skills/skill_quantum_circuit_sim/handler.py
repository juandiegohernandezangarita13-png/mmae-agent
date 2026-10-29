"""
Handler para skill_quantum_circuit_sim.
Simulador cuántico vectorial autocontenido en Python puro.
"""
from typing import Dict, Any, List
import cmath
import math
import random

def handle(**kwargs) -> Dict[str, Any]:
    action = kwargs.get("action", "simulate_circuit")
    num_qubits = min(max(int(kwargs.get("num_qubits", 2)), 1), 8)
    gates = kwargs.get("gates") or []

    # Estado inicial: |00...0>
    dim = 2 ** num_qubits
    state = [0.0 + 0.0j] * dim
    state[0] = 1.0 + 0.0j

    # Aplicar compuertas cuánticas
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    for g in gates:
        g_name = g.get("gate", "").upper()
        target = int(g.get("target", 0))

        if g_name == "H":
            for i in range(dim):
                if not (i & (1 << target)):
                    j = i | (1 << target)
                    u = state[i]
                    v = state[j]
                    state[i] = (u + v) * inv_sqrt2
                    state[j] = (u - v) * inv_sqrt2
        elif g_name == "X":
            for i in range(dim):
                if not (i & (1 << target)):
                    j = i | (1 << target)
                    state[i], state[j] = state[j], state[i]
        elif g_name == "Z":
            for i in range(dim):
                if (i & (1 << target)):
                    state[i] = -state[i]
        elif g_name == "CNOT":
            ctrl = int(g.get("control", 0))
            for i in range(dim):
                if (i & (1 << ctrl)) and not (i & (1 << target)):
                    j = i | (1 << target)
                    state[i], state[j] = state[j], state[i]

    # Calcular probabilidades
    probs = {}
    for i in range(dim):
        p = round((state[i].real ** 2 + state[i].imag ** 2), 4)
        if p > 0:
            bin_str = bin(i)[2:].zfill(num_qubits)
            probs[f"|{bin_str}>"] = p

    return {
        "status": "success",
        "num_qubits": num_qubits,
        "gates_applied": len(gates),
        "probabilities": probs,
        "dimension": dim
    }
