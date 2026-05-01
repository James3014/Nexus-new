import pytest
from nexus.core.state_contracts import NexusState, NexusDerivation, DerivationStep

def test_nexus_state_with_derivation():
    derivation = NexusDerivation(
        task_id="T3-4",
        goal="Implement Derivation Model",
        steps=[
            DerivationStep(
                step_index=0,
                operation="Define Model",
                rationale="Required for evidence closure"
            )
        ]
    )
    
    state = NexusState(
        task_id="T3-4",
        derivation=derivation
    )
    
    assert state.derivation is not None
    assert state.derivation.task_id == "T3-4"
    assert len(state.derivation.steps) == 1
    assert state.derivation.steps[0].operation == "Define Model"
    print("NexusState with Derivation verified.")

if __name__ == "__main__":
    test_nexus_state_with_derivation()
