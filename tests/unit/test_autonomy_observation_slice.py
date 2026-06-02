import pytest
from nexus.engine.autonomy_observation import AutonomyObserver, AutonomyObservationReceipt

class MockContext:
    def __init__(self, instance_id, wall_time, attempt, failure_reason=""):
        self.instance_id = instance_id
        self.wall_time_sec = wall_time
        self.attempt = attempt
        self.failure_reason = failure_reason
        self.recommended_flow = "local_repair"
        self.syntax_gate_passed = True
        self.token_total_estimated = 5000
        self.final_patch = "diff..."

def test_autonomy_observer_capture_logic():
    # Arrange
    ctx = MockContext(instance_id="task-001", wall_time=120.5, attempt=2)
    observer = AutonomyObserver()
    task_metadata = {"task_class": "algebraic", "model_class": "local-14b"}
    
    # Act
    receipt = observer.capture_observation(ctx, task_metadata)
    
    # Assert
    assert receipt.task_id == "task-001"
    assert receipt.task_class == "algebraic"
    assert receipt.wall_time_sec == 120.5
    assert receipt.retry_count == 2
    assert receipt.observation_only is True
    assert receipt.promotion_effect == "none"

def test_autonomy_observer_serialization():
    receipt = AutonomyObservationReceipt(task_id="t1", wall_time_sec=10.0)
    data = receipt.to_dict()
    assert data["schema_version"] == "autonomy_observation_receipt.v1"
    assert data["wall_time_sec"] == 10.0
