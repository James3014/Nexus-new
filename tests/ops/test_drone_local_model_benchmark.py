import json
import pytest
from unittest.mock import patch, MagicMock

from scripts.ops.drone_local_model_benchmark import run_benchmark

@patch("scripts.ops.drone_local_model_benchmark.Path")
@patch("scripts.ops.drone_local_model_benchmark.TacticalDrone")
def test_drone_benchmark_no_inflation_and_threshold(mock_tactical_drone, mock_path, tmp_path):
    mock_instance = MagicMock()
    mock_tactical_drone.return_value = mock_instance
    
    # 建立失敗的測資：所有 task 皆無有效動作（UNKNOWN）
    mock_instance.sense_think_act.return_value = {
        "outcome": "SUCCESS",
        "traces": [
            {"phase": "THINK", "message": "Thinking..."},
            {"phase": "DECISION", "message": "UNKNOWN: skip"},
            {"phase": "SENSE", "message": "Result: Failed"}
        ]
    }
    
    # 強制將寫入路徑導向 tmp_path 避免寫入真的資料夾
    mock_path_instance = MagicMock()
    mock_path.return_value = mock_path_instance
    mock_path_instance.resolve.return_value.parent.parent.parent = tmp_path
    
    run_benchmark()
    
    report_file = tmp_path / ".nexus/reports/drone/local_model_benchmark.json"
    assert report_file.exists()
    
    with open(report_file, "r") as f:
        report = json.load(f)
        
    # 驗證輸出欄位
    assert "legal_actions_raw" in report
    assert "tool_success_raw" in report
    assert "invalid_actions_raw" in report
    assert "false_success_raw" in report
    assert "total_tasks" in report
    
    # 驗證未造數（數字不抬高）
    assert report["legal_action_rate"] < 0.95
    assert report["tool_exec_success_rate"] < 0.80
    assert report["legal_actions_raw"] == 0
    assert report["tool_success_raw"] == 0
    
    # 驗證 threshold fail 標記
    assert report["threshold_passed"] is False
    assert "failure_reasons" in report
    assert len(report["failure_reasons"]) > 0