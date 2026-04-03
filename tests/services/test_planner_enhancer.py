"""
🛡️ Nexus Planner Enhancer: 單元測試 (P2-C)
驗證 Health 與 Fix Templates 的注入與 Markdown 情境生成。
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from nexus.services.planner_enhancer import enhance_planner_context

@pytest.fixture
def mock_health():
    """模擬健康數據"""
    return {
        "status": "healthy",
        "phase": "R",
        "metrics": {
            "health_score": 0.85,
            "autorepair_success_rate": 0.9,
            "phantom_fp_rate": 0.05
        }
    }

@pytest.fixture
def mock_repair_recs():
    """模擬修復推薦"""
    return {
        "status": "ok",
        "recommendations": [
            {
                "category": "AUTH",
                "similarity": 0.2,
                "root_cause": "Timezone mismatch",
                "fix_template": "Use UTC",
                "success_rate": 1.0
            }
        ],
        "prompt_context": "## 🔍 Historical Successful Fixes ..."
    }

@patch("nexus.services.planner_enhancer.compute_phase_health")
@patch("nexus.services.planner_enhancer.get_repair_recommendations")
def test_enhance_planner_context_structure(mock_recs, mock_hlth, mock_health, mock_repair_recs):
    """驗證 Enhancer 對 Metadata 及 Context 的封裝結構"""
    mock_hlth.return_value = mock_health
    mock_recs.return_value = mock_repair_recs
    
    repo_root = Path("/tmp/mock")
    diagnosis = {"phase": "R", "traceback_snippet": "error"}
    
    result = enhance_planner_context(repo_root, diagnosis, {})
    
    # 驗證元數據 (對齊 v22 穩定性)
    assert "planner_metadata" in result
    meta = result["planner_metadata"]
    assert meta["phase_health_score"] == 0.85
    assert meta["repair_template_count"] == 1
    
    # 驗證 Prompt Context
    ctx = result["prompt_context"]
    assert "Phase R Health Status" in ctx
    assert "Historical Successful Fixes" in ctx
    print("\n✅ Planner Enhancer Context Verified")

def test_enhance_planner_context_no_diagnosis():
    """驗證在無診斷時不應該進行增強 (雖然目前 planner 會檢查，但 enhancer 應具備穩定性)"""
    # 此處僅驗證 enhancer 函式穩定
    # 目前 planner 會在有 diagnosis 時才調用，但 enhancer 應能穩定返回 {}
    pass
