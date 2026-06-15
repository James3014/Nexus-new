import pytest
from nexus.services.local_deliberation_lane import LocalDeliberationLane, DeliberationFitness, DeliberationResult

def test_deliberation_lane_should_trigger():
    lane = LocalDeliberationLane(force_simulation=True)
    
    # 1. Normal task should not trigger
    assert lane.should_trigger({"task_type": "bugfix", "value_tier": 10.0}) is False
    
    # 2. High uncertainty explicit flag should trigger
    assert lane.should_trigger({"high_uncertainty": True}) is True
    
    # 3. Research task should trigger
    assert lane.should_trigger({"task_type": "research"}) is True
    
    # 4. Repair-review task should trigger
    assert lane.should_trigger({"task_type": "repair-review"}) is True
    
    # 5. High value task (value_tier >= 100.0) should trigger
    assert lane.should_trigger({"value_tier": 150.0}) is True

def test_robust_json_parse_handles_markdown_and_variants():
    lane = LocalDeliberationLane(force_simulation=True)
    
    # Standard JSON
    assert lane._robust_json_parse('{"a": 1}') == {"a": 1}
    
    # Markdown wrapped JSON
    assert lane._robust_json_parse('```json\n{"a": 1}\n```') == {"a": 1}
    
    # Python-like dict output with single quotes
    assert lane._robust_json_parse("{'a': 1, 'b': True}") == {"a": 1, "b": True}

def test_deliberation_simulation_fallback():
    lane = LocalDeliberationLane(force_simulation=True)
    
    task_context = {
        "task_id": "test-task-101",
        "candidates": [
            {"id": "cand-1", "cost": 0.5},
            {"id": "cand-2", "cost": 1.2}
        ]
    }
    
    result = lane.deliberate(task_context)
    
    assert isinstance(result, DeliberationResult)
    assert result.success is True
    assert result.selected_candidate_id == "cand-1"
    assert result.confidence == 0.85
    assert result.verdict == "pass"
    assert result.fallback_used is True
    assert isinstance(result.fitness, DeliberationFitness)
    assert result.fitness.confidence_score == 0.85
    assert result.fitness.is_stable is True

def test_deliberation_empty_candidates():
    lane = LocalDeliberationLane(force_simulation=True)
    
    result = lane.deliberate({"task_id": "test-task-102", "candidates": []})
    
    assert result.success is True
    assert result.selected_candidate_id == ""
    assert "no_candidates" in result.synthesis_notes
    assert result.fallback_used is True
