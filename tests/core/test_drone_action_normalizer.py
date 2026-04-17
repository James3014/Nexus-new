import pytest
from pathlib import Path
from nexus.core.drone_engine import TacticalDrone, LocalBonsaiBrain

@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "MUSE_PROTO.md").write_text("# Mock Protocol\n- Be good.")
    return tmp_path

def test_normalize_expanded_aliases():
    drone = TacticalDrone("test", Path("."))
    assert drone.normalize_action("SAVE") == "EDIT"
    assert drone.normalize_action("READ_FILE") == "BASH"
    assert drone.normalize_action("MKDIR") == "BASH"
    assert drone.normalize_action("STOP") == "DONE"
    assert drone.normalize_action("SUCCESS") == "DONE"

def test_done_rejected_if_no_tool(project_root, monkeypatch):
    drone = TacticalDrone("test-done-rej", project_root, max_rounds=3)
    def mock_ask(self, messages):
        return {"action": "DONE", "reasoning": "done immediately"}
    monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
    drone.local_brain.ask_structured = mock_ask.__get__(drone.local_brain, LocalBonsaiBrain)
    
    res = drone.sense_think_act("task")
    # Should stay in REPAIR_NEEDED and continue loop until max_rounds
    assert res["outcome"] == "REPAIR_NEEDED"
    assert any("DONE rejected" in str(t) for t in res["traces"])

def test_done_accepted_after_tool(project_root, monkeypatch):
    drone = TacticalDrone("test-done-acc", project_root, max_rounds=3)
    call_count = 0
    def mock_ask(self, messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"action": "BASH", "command": "echo hello", "reasoning": "tool"}
        return {"action": "DONE", "reasoning": "done after tool"}
    monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
    drone.local_brain.ask_structured = mock_ask.__get__(drone.local_brain, LocalBonsaiBrain)
    
    res = drone.sense_think_act("task")
    assert res["outcome"] == "SUCCESS"

def test_three_strike_failure(project_root, monkeypatch):
    drone = TacticalDrone("test-strikes", project_root, max_rounds=5)
    call_count = 0
    def mock_ask(self, messages):
        nonlocal call_count
        call_count += 1
        return {"action": "FLY", "reasoning": "invalid"}
    monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
    drone.local_brain.ask_structured = mock_ask.__get__(drone.local_brain, LocalBonsaiBrain)
    
    res = drone.sense_think_act("task")
    assert res["outcome"] == "FAIL"
    assert any("Invalid action 3rd attempt" in str(t) for t in res["traces"])

def test_pwd_fallback_on_second_fail(project_root, monkeypatch):
    # Use belief_score=3.0 so that 3.0 * 0.5 * 0.5 = 0.75 (>0.5 threshold)
    drone = TacticalDrone("test-fallback", project_root, max_rounds=5, belief_score=3.0) 
    call_count = 0
    def mock_ask(self, messages):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return {"action": "FLY", "reasoning": "invalid"}
        return {"action": "DONE", "reasoning": "fixed"}
    monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
    drone.local_brain.ask_structured = mock_ask.__get__(drone.local_brain, LocalBonsaiBrain)
    
    res = drone.sense_think_act("task")
    assert any("BASH Result: {'exit_code': 0" in str(t) for t in res["traces"])
    assert res["outcome"] == "SUCCESS"
