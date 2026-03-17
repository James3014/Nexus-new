import pytest
from nexus.core.state_contracts import NexusState
from nexus.engine.health.evaluator import HealthEvaluator

@pytest.fixture
def state():
    s = NexusState(task_id="test-health")
    s.total_token_usage = 1000
    s.metadata["repair_attempts"] = 2
    return s

@pytest.fixture
def evaluator():
    return HealthEvaluator()

def test_evaluate_success_low_cost(state, evaluator):
    score = evaluator.evaluate(state, success=True)
    assert score >= 80
    assert state.health_metrics.status == "HEALTHY"
    assert state.health_metrics.test_pass_rate == 1.0

def test_evaluate_failure_high_retry(state, evaluator):
    state.metadata["repair_attempts"] = 5
    state.total_token_usage = 8000
    score = evaluator.evaluate(state, success=False)
    assert score < 50
    assert state.health_metrics.status == "CRITICAL"
    assert state.health_metrics.test_pass_rate == 0.0
