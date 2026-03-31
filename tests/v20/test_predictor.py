import pytest
from pathlib import Path
from nexus.learning.latent_predictor_v20 import LatentPredictorV20
from unittest.mock import MagicMock

@pytest.fixture
def predictor():
    root = Path("/Users/jameschen/Workspace/nexus")
    p = LatentPredictorV20(root)
    # Mock RAG 為控制變因
    p.rag = MagicMock()
    return p

def test_forecast_roi_high_confidence(predictor):
    """驗證當存在多筆歷史數據時，預測器能給出 HIGH 置信度與準確 ROI。"""
    predictor.rag.query.return_value = [
        {"task": "Refactor core", "metadata": {"actual_tokens": 1200, "actual_latency": 150}},
        {"task": "Redesign engine", "metadata": {"actual_tokens": 1800, "actual_latency": 200}},
        {"task": "Modify orchestrator", "metadata": {"actual_tokens": 1500, "actual_latency": 170}}
    ]
    
    result = predictor.forecast_roi("Refactor the swarm engine")
    
    assert result["confidence"] == "HIGH"
    assert result["matches"] == 3
    assert result["est_tokens"] == 1500  # 平均值
    assert result["roi_score"] > 0.8     # (1 - 1500/10000)

def test_forecast_roi_cold_start(predictor):
    """驗證當無歷史數據時，預測器執行冷啟動策略。"""
    predictor.rag.query.return_value = []
    
    result = predictor.forecast_roi("Brand new experimental task")
    
    assert result["confidence"] == "LOW"
    assert result["evidence"] == "cold_start_heuristic"

def test_predict_risk_high(predictor):
    """驗證風險感應器能識別危險模式並觸發高拒絕機率。"""
    # 含有 "subprocess" 關鍵字
    result = predictor.predict_risk("Execute a risky subprocess command")
    
    assert result["status"] == "CAUTION"
    assert any(r["type"] == "subprocess" for r in result["risks"])
    assert result["reject_prob"] > 0.4

def test_predict_risk_clear(predictor):
    """驗證正常任務不觸發風險。"""
    result = predictor.predict_risk("Update documentation for the readme")
    
    assert result["status"] == "CLEAR"
    assert result["reject_prob"] == 0.05
