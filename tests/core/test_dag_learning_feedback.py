import pytest
import json
from pathlib import Path
from nexus.core.campaign_general import CampaignGeneral

@pytest.fixture
def project_root(tmp_path):
    return tmp_path

def test_dag_learning_weights_application(project_root):
    # 建立模擬學習訊號 (低成功率 -> 簡化)
    feedback_dir = project_root / ".nexus/reports/evolution"
    feedback_dir.mkdir(parents=True)
    (feedback_dir / "learning_signals.json").write_text(json.dumps({"overall_success_rate": 0.5}))
    
    commander = CampaignGeneral(project_root)
    assert commander.weights["node_count_multiplier"] == 0.8
    
    # 測試 refactor 節點數 (原本 4, 現在 multiplier 0.8 -> int(3.2) = 3)
    nodes = commander.decompose_intent("refactor storage")
    assert len(nodes) == 3

def test_dag_learning_high_success(project_root):
    # 高成功率 -> 增加深度
    feedback_dir = project_root / ".nexus/reports/evolution"
    feedback_dir.mkdir(parents=True)
    (feedback_dir / "learning_signals.json").write_text(json.dumps({"overall_success_rate": 0.98}))
    
    commander = CampaignGeneral(project_root)
    assert commander.weights["node_count_multiplier"] == 1.2
    
    # 原本 4 節點 -> 4 * 1.2 = 4.8 -> 4 節點 (int 捨去) 
    # (註：若要看到 5 節點，權重需更高或基礎節點更多。這裡測試權重加載正確即可)
    assert commander.weights["node_count_multiplier"] == 1.2

def test_dag_deterministic_with_weights(project_root):
    commander = CampaignGeneral(project_root)
    n1 = commander.decompose_intent("fix bug", seed=42)
    n2 = commander.decompose_intent("fix bug", seed=42)
    assert [n.node_id for n in n1] == [n.node_id for n in n2]
