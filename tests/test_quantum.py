from nexus.core.quantum_logic import calculate_stability
def test_baseline():
    assert calculate_stability(0.5) == "STABLE"
