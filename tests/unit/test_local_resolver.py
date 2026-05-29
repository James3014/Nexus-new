import pytest
from unittest.mock import MagicMock
from nexus.services.local_heal.localizer import Localizer

def test_localizer_returns_relevant_files():
    # 建立 mock 的 repository 或 LanceDB 查詢 seam
    mock_repo = MagicMock()
    mock_repo.search_fts.return_value = [
        {"source_path": "nexus/services/gateway.py", "record_id": "r1"},
        {"source_path": "nexus/services/predictor.py", "record_id": "r2"}
    ]
    
    localizer = Localizer(repository=mock_repo)
    results = localizer.locate(issue_description="gateway high latency issue")
    
    # 驗證返回結果是否正確解耦為檔案清單與分數資訊
    assert len(results) == 2
    assert results[0]["file_path"] == "nexus/services/gateway.py"
    assert results[1]["file_path"] == "nexus/services/predictor.py"

def test_sandbox_executor_runs_test_and_summarizes():
    from nexus.services.local_heal.sandbox import SandboxExecutor
    
    # 建立 mock 的 subprocess 執行結果
    mock_runner = MagicMock()
    # 模擬測試失敗並包含冗長的 traceback
    mock_runner.run.return_value = (
        False, 
        "AssertionError: 2 != 3\n"
        "Traceback (most recent call last):\n"
        "  File \"test_gateway.py\", line 15, in test_latency\n"
        "    assert result == expected\n"
        "AssertionError: assert 2 == 3\n"
        "---------------------- Generated Noise ----------------------\n"
        "Lots of internal logs and standard library warnings..."
    )
    
    sandbox = SandboxExecutor(runner=mock_runner)
    result = sandbox.run_and_summarize(
        file_path="nexus/services/gateway.py",
        patch_code="def new_func(): pass",
        test_command="pytest tests/unit/test_gateway.py"
    )
    
    assert result["success"] is False
    # 確保冗長的錯誤訊息被「語義濃縮」
    assert "AssertionError" in result["error_summary"]
    assert "Generated Noise" not in result["error_summary"]

def test_patch_evaluator_decides_rollback_on_failed_attempts():
    from nexus.services.local_heal.evaluator import PatchTreeEvaluator
    
    evaluator = PatchTreeEvaluator()
    
    # 初始狀態：0 個錯誤
    # 第一個 patch：10 個錯誤 (退步，此時應 rollback)
    action1 = evaluator.evaluate_attempt(failed_test_count=10, patch_hash="h1")
    assert action1["action"] == "rollback"
    
    # 第二個 patch：0 個錯誤 (改善)
    action2 = evaluator.evaluate_attempt(failed_test_count=0, patch_hash="h2")
    assert action2["action"] == "accept"


