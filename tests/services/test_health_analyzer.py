"""
🛡️ Nexus Health Analyzer: 單元測試 (P2-C)
驗證 Phase 健康指標計算邏輯與 v22 分數權重。
"""

import pytest
import pandas as pd
import json
from unittest.mock import MagicMock, patch
from pathlib import Path
from datetime import datetime, timezone, timedelta

from nexus.services.health_analyzer import compute_phase_health

@pytest.fixture
def mock_lancedb_hits():
    """模擬 LanceDB 查詢結果"""
    # 建立 10 個事件，8 個成功，2 個失敗
    payloads = []
    for i in range(8):
        payloads.append({
            "repair_success": True, 
            "phantom_blocked": False,
            "pattern_reuse": 75.0,
            "timestamp_utc": "2026-04-01T12:00:00Z",
            "phase": "R"
        })
    for i in range(2):
        payloads.append({
            "repair_success": False, 
            "phantom_blocked": True,
            "pattern_reuse": 20.0,
            "timestamp_utc": "2026-04-01T13:00:00Z",
            "phase": "R"
        })
    
    # 建立 DataFrame 模擬 table.search().to_pandas()
    df = pd.DataFrame({
        "record_type": ["outcome_event"] * 10,
        "phase": ["R"] * 10,
        "payload_json": [json.dumps(p) for p in payloads],
        "created_at_utc": ["2026-04-01T12:00:00Z"] * 10,
        "score_hint": [0.75] * 8 + [0.20] * 2
    })
    return df

@patch("nexus.services.health_analyzer.connect_memory_db")
def test_compute_phase_health_logic(mock_connect, mock_lancedb_hits):
    """驗證健康指標計算與 v22 權重 0.8 / 0.2"""
    mock_table = MagicMock()
    mock_table.search.return_value.where.return_value.to_pandas.return_value = mock_lancedb_hits
    
    mock_db = MagicMock()
    mock_db.open_table.return_value = mock_table
    mock_connect.return_value = mock_db
    
    repo_root = Path("/tmp/mock_nexus")
    result = compute_phase_health(repo_root, "R")
    
    assert result["status"] == "healthy"
    metrics = result["metrics"]
    
    # 指標驗證
    assert metrics["total_events"] == 10
    assert metrics["autorepair_success_rate"] == 0.8 # 8/10
    assert metrics["phantom_fp_rate"] == 0.2 # 2/10
    
    # Pattern Reuse 平均: (0.75*8 + 0.2*2) / 10 = (6 + 0.4) / 10 = 0.64
    assert metrics["pattern_reuse_rate"] == 0.64
    
    # Health Score: 0.8 * 0.8 + 0.2 * 0.64 = 0.64 + 0.128 = 0.768
    assert metrics["health_score"] == 0.768
    print(f"\n✅ Health Analyzer Logic Verified: {metrics}")
