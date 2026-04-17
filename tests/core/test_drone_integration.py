import pytest
import json
from pathlib import Path
from nexus.core.campaign_general import CampaignGeneral
from nexus.core.skill_assembler import SkillAssembler
from nexus.core.drone_engine import TacticalDrone, LocalBonsaiBrain

@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "MUSE_PROTO.md").write_text("# Mock Protocol\n- Be good.")
    return tmp_path

def test_drone_execution_and_crystal(project_root, monkeypatch):
    commander = CampaignGeneral(project_root)
    
    def mock_ask(self, messages):
        return {"action": "DONE", "reasoning": "Mocked done"}
    monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)

    def mock_execute(node_id):
        node = commander.campaign_map[node_id]
        drone = TacticalDrone(f"drone-{node_id}", project_root, node.belief_confidence)
        drone.local_brain.ask_structured = mock_ask.__get__(drone.local_brain, LocalBonsaiBrain)
        res = drone.sense_think_act(node.intent, [])
        node.status = res["outcome"]
        node.belief_confidence = res["belief_final"]
        report_dir = project_root / ".nexus/reports/drones"
        report_dir.mkdir(parents=True, exist_ok=True)
        drone.save_evolution_crystal(report_dir / f"{node_id}_crystal.json")
        return res
    monkeypatch.setattr(commander, "execute_node_via_drone", mock_execute)

    commander.decompose_intent("implement memory-service with high stability")
    executable = commander.get_executable_nodes()
    assert len(executable) > 0
    node = executable[0]
    result = commander.execute_node_via_drone(node.node_id)
    assert result["outcome"] == "SUCCESS"
    assert result["belief_final"] == 1.0

def test_drone_self_healing_belief(project_root, monkeypatch):
    drone = TacticalDrone("test-drone", project_root, belief_score=1.0)
    
    call_count = 0
    def mock_ask(self_brain, messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"action": "BASH", "command": "false", "reasoning": "Mocking failure"}
        return {"action": "DONE", "reasoning": "Fixed it"}
        
    monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
    drone.local_brain.ask_structured = mock_ask.__get__(drone.local_brain, LocalBonsaiBrain)
    
    result = drone.sense_think_act("this task will fail and need repair", tools=[])
    
    assert result["belief_final"] < 1.0
    assert any(t["phase"] == "SELF-HEAL" for t in result["traces"])

def test_skill_assembler_soul_alignment(project_root):
    assembler = SkillAssembler(project_root)
    skill_name = assembler.assemble_new_skill("fix buffer overflow", "logic gap")
    skill_md = project_root / "skills" / skill_name / "SKILL.md"
    content = skill_md.read_text()
    assert "🧬 Soul Trinity Mapping" in content
    assert "MemPalace" in content
    assert "MUSE_PROTO" in content

def test_missing_action(project_root, monkeypatch):
    drone = TacticalDrone("test-missing-action", project_root)
    def mock_ask(self, messages):
        return {"reasoning": "I forgot to include an action"}
    monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
    drone.local_brain.ask_structured = mock_ask.__get__(drone.local_brain, LocalBonsaiBrain)
    
    res = drone.sense_think_act("do something")
    assert res["outcome"] == "FAIL"

def test_unknown_action(project_root, monkeypatch):
    drone = TacticalDrone("test-unknown-action", project_root)
    def mock_ask(self, messages):
        return {"action": "JUMP", "reasoning": "I want to jump"}
    monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
    drone.local_brain.ask_structured = mock_ask.__get__(drone.local_brain, LocalBonsaiBrain)
    
    res = drone.sense_think_act("do something")
    assert res["outcome"] == "FAIL"

def test_server_down_failure(project_root, monkeypatch):
    import requests
    drone = TacticalDrone("test-server-down", project_root)
    
    def mock_post(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Mocked Connection Error")
        
    monkeypatch.setattr(requests, "post", mock_post)
    res = drone.sense_think_act("do something")
    assert res["outcome"] == "FAIL"

def test_partial_fail_aggregation(project_root, monkeypatch):
    commander = CampaignGeneral(project_root)
    commander.decompose_intent("refactor multiple things")
    
    nodes = list(commander.campaign_map.values())
    nodes[0].status = "SUCCESS"
    nodes[1].status = "FAIL"
    if len(nodes) > 2:
        nodes[2].status = "SUCCESS"
        
    report_dir = project_root / ".nexus/reports"
    commander.generate_evolution_report(report_dir)
    
    report_path = report_dir / "pipeline_evolution_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["execution_outcome"] == "PARTIAL"