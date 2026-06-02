import pytest
from nexus.engine.slice_planner import VerticalSlicePlanner

def test_slice_planner_detect_horizontal():
    planner = VerticalSlicePlanner()
    outline = "1. Finish all API endpoints.\n2. Work on DB schema."
    valid, reason = planner.validate_outline(outline)
    assert valid is False
    assert "HORIZONTAL_SLICE_DETECTED" in reason

def test_slice_planner_missing_verify():
    planner = VerticalSlicePlanner()
    outline = "1. Add a field to API and update Service."
    valid, reason = planner.validate_outline(outline)
    assert valid is False
    assert "NO_VERIFY_COMMAND" in reason

def test_slice_planner_valid_vertical():
    planner = VerticalSlicePlanner()
    outline = (
        "1. Implement User API + Service slice. Verify with pytest tests/auth.\n"
        "Rollback: revert User schema change if failed."
    )
    valid, reason = planner.validate_outline(outline)
    assert valid is True
