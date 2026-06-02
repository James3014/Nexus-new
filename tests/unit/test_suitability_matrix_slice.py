import pytest
from nexus.engine.autonomy_observation import (
    SuitabilityAssessor, 
    AutonomyObservationReceipt, 
    LocalModelSuitabilityMatrix
)

def test_suitability_assessor_recommendation():
    # Arrange: 建立一組觀測數據，其中 "algebraic" 表現良好，"semantic" 表現較差
    observations = [
        AutonomyObservationReceipt(task_class="algebraic", stop_layer_matched=True, syntax_gate_passed=True),
        AutonomyObservationReceipt(task_class="algebraic", stop_layer_matched=True, syntax_gate_passed=True),
        AutonomyObservationReceipt(task_class="semantic", stop_layer_matched=False, syntax_gate_passed=True),
    ]
    assessor = SuitabilityAssessor()
    
    # Act
    matrix = assessor.assess_suitability(observations)
    
    # Assert
    assert matrix.verdicts["algebraic"].small_model_recommended is True
    assert matrix.verdicts["semantic"].small_model_recommended is False
    assert matrix.promotion_allowed is False # 預設不允許晉升

def test_suitability_matrix_serialization():
    observations = [AutonomyObservationReceipt(task_class="env", stop_layer_matched=True)]
    assessor = SuitabilityAssessor()
    matrix = assessor.assess_suitability(observations)
    
    data = matrix.to_dict()
    assert data["schema_version"] == "local_model_suitability_matrix.v1"
    assert "env" in data["verdicts"]
