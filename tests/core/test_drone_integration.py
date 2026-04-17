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

def test_drone_execution_and_crystal(project_root):
    # 1. 指揮官初始化
    commander = CampaignGeneral(project_root)
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
    
    # 3. 檢查結晶 (Artifacts)
    crystal_path = project_root / f".nexus/reports/drones/{node_id}_crystal.json"
    assert crystal_path.exists()
    crystal = json.loads(crystal_path.read_text())
    assert crystal["drone_id"] == f"drone-{node_id}"
    assert len(crystal["tracelog"]) > 0

def test_drone_self_healing_belief(project_root):
    # 模擬一個包含 "fail" 的任務
    drone = TacticalDrone("test-drone", project_root, belief_score=1.0)
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
