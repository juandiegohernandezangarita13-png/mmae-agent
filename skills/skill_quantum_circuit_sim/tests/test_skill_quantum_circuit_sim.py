"""
Tests unitarios para skill_quantum_circuit_sim.
"""
import unittest
import handler

class TestQuantumCircuitSim(unittest.TestCase):
    def test_bell_state_generation(self):
        # Crear estado de Bell (|00> + |11>) / sqrt(2)
        gates = [
            {"gate": "H", "target": 0},
            {"gate": "CNOT", "control": 0, "target": 1}
        ]
        res = handler.handle(action="simulate_circuit", num_qubits=2, gates=gates)
        self.assertEqual(res.get("status"), "success")
        probs = res.get("probabilities", {})
        self.assertAlmostEqual(probs.get("|00>", 0), 0.5, delta=0.05)
        self.assertAlmostEqual(probs.get("|11>", 0), 0.5, delta=0.05)

    def test_single_qubit_not_gate(self):
        gates = [{"gate": "X", "target": 0}]
        res = handler.handle(action="simulate_circuit", num_qubits=1, gates=gates)
        self.assertEqual(res.get("status"), "success")
        probs = res.get("probabilities", {})
        self.assertEqual(probs.get("|1>", 0), 1.0)

if __name__ == "__main__":
    unittest.main()
