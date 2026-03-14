import pytest
from pathlib import Path
from nexus.engine.coordinator import NexusEngine

def test_engine_initialization(tmp_path):
    """測試引擎初始化與目錄建立。"""
    engine = NexusEngine(project_root=tmp_path, silent=True)
    assert engine.project_root == tmp_path
    assert engine.run_dir.exists()
    assert engine.state_io is not None
    assert engine.commander is not None

def test_engine_predict_logic(tmp_path):
    """測試風險預判邏輯的分數計算。"""
    engine = NexusEngine(project_root=tmp_path, silent=True)
    
    # 測試 HTML 任務風險
    res = engine.run_predict("Fix HTML layout issues", {})
    assert res["risk_score"] >= 3.0
    assert any(r["id"] == "JS_CONFLICT_RISK" for r in res["risks"])
    
    # 測試文件讀取風險
    res = engine.run_predict("Read local files", {})
    assert res["risk_score"] >= 8.5
    assert any(r["id"] == "BROWSER_SANDBOX_RISK" for r in res["risks"])
