import pytest
from nexus.core.state_contracts import NexusState
from nexus.engine.metrics.token_accumulator import TokenAccumulator

@pytest.fixture
def state():
    return NexusState(task_id="test-task")

@pytest.fixture
def accumulator():
    return TokenAccumulator()

def test_accumulator_record_raw(state, accumulator):
    # Setup response data
    res_data = {
        "token_raw_model": 100,
        "token_fallback_est": 0,
        "token_capture_status": "ok"
    }
    
    accumulator.record(state, phase="X", res_data=res_data, overhead=50)
    
    assert state.token_raw_model == 100
    assert state.token_fallback_est == 0
    assert state.token_system_overhead == 50
    assert state.total_token_usage == 150
    assert state.phase_tokens["X"] == 150
    assert state.token_capture_status == "ok"

def test_accumulator_record_fallback(state, accumulator):
    res_data = {
        "token_raw_model": 0,
        "token_fallback_est": 80,
        "token_capture_status": "fallback_est"
    }
    
    accumulator.record(state, phase="R", res_data=res_data, overhead=100)
    
    assert state.token_raw_model == 0
    assert state.token_fallback_est == 80
    assert state.token_system_overhead == 100
    assert state.total_token_usage == 180
    assert state.phase_tokens["R"] == 180
    assert state.token_capture_status == "fallback_est"

def test_accumulator_invalid_phase(state, accumulator):
    res_data = {"token_raw_model": 10}
    with pytest.raises(ValueError, match="Invalid phase"):
        accumulator.record(state, phase="Z", res_data=res_data)

def test_accumulator_cumulative(state, accumulator):
    # Phase 1: X
    accumulator.record(state, phase="X", res_data={"token_raw_model": 100, "token_capture_status": "ok"}, overhead=50)
    # Phase 2: R
    accumulator.record(state, phase="R", res_data={"token_raw_model": 200, "token_capture_status": "ok"}, overhead=100)
    
    assert state.token_raw_model == 300
    assert state.token_system_overhead == 150
    assert state.total_token_usage == 450
    assert state.phase_tokens["X"] == 150
    assert state.phase_tokens["R"] == 300
def test_accumulator_total_property(state, accumulator):
    accumulator.record(state, phase="P", res_data={"token_raw_model": 10}, overhead=5)
    assert accumulator.total_tokens_used == 15
    accumulator.record(state, phase="X", res_data={"token_raw_model": 20}, overhead=5)
    assert accumulator.total_tokens_used == 40
