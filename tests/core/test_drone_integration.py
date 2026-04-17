import pytest
import json
from pathlib import Path
from nexus.core.campaign_general import CampaignGeneral
from nexus.core.skill_assembler import SkillAssembler
from nexus.core.drone_engine import TacticalDrone

@pytest.fixture
def project_root(tmp_path):
    # 建立必要的目錄與規約檔
    (tmp_path / "MUSE_PROTO.md").write_text("# Mock Protocol\n- Be good.")
    return tmp_path

def test_drone_execution_and_crystal(project_root, monkeypatch):
    # 1. 指揮官初始化
    commander = CampaignGeneral(project_root)
    
    # 避免真實 LLM 呼叫，直接修改 execute_node_via_drone 行為
    original_execute = commander.execute_node_via_drone
    def mock_execute(node_id):
        node = commander.campaign_map[node_id]
        drone = TacticalDrone(f"drone-{node_id}", project_root, node.belief_confidence)
        drone.gateway = None  # Force mock mode
        res = drone.sense_think_act(node.intent, [])
        node.status = res["outcome"]
        node.belief_confidence = res["belief_final"]
        
        # 寫入 mock 結晶
        report_dir = project_root / ".nexus/reports/drones"
        report_dir.mkdir(parents=True, exist_ok=True)
        drone.save_evolution_crystal(report_dir / f"{node_id}_crystal.json")
        return res
    monkeypatch.setattr(commander, "execute_node_via_drone", mock_execute)

    commander.decompose_intent("implement memory-service with high stability")
    
    # 動態獲取第一個可執行的節點
    executable = commander.get_executable_nodes()
    assert len(executable) > 0
    node = executable[0]
    node_id = node.node_id
    
    # 2. 委派執行
    result = commander.execute_node_via_drone(node_id)
    assert result["outcome"] == "SUCCESS"
    assert result["belief_final"] == 1.0

def test_drone_self_healing_belief(project_root):
    # 模擬一個包含 "fail" 的任務
    drone = TacticalDrone("test-drone", project_root, belief_score=1.0)
    drone.gateway = None # Force mock mode
    result = drone.sense_think_act("this task will fail and need repair", tools=[])
    
    # 驗證 Belief 分數下降 (觸發了模擬的修復路徑)
    assert result["belief_final"] < 1.0
    assert any(t["phase"] == "SELF-HEAL" for t in result["traces"])

def test_skill_assembler_soul_alignment(project_root):
    assembler = SkillAssembler(project_root)
    skill_name = assembler.assemble_new_skill("fix buffer overflow", "logic gap")
    
    skill_md = project_root / "skills" / skill_name / "SKILL.md"
    content = skill_md.read_text()
    
    # 驗證靈魂對齊標記
    assert "🧬 Soul Trinity Mapping" in content
    assert "MemPalace" in content
    assert "MUSE_PROTO" in content