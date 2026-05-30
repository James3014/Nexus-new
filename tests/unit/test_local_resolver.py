import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from nexus.services.local_heal.localizer import Localizer

def test_hybrid_localizer_with_bm25_and_ast():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # 1. 建立一些測試 Python 檔案
        file_a = tmp_path / "gateway.py"
        file_a.write_text(
            "class GatewayService:\n"
            "    def handle_request(self):\n"
            "        pass\n", 
            encoding="utf-8"
        )
        
        file_b = tmp_path / "predictor.py"
        file_b.write_text(
            "class LatencyPredictor:\n"
            "    def predict_latency(self):\n"
            "        pass\n", 
            encoding="utf-8"
        )
        
        file_c = tmp_path / "unrelated.py"
        file_c.write_text(
            "class UnrelatedWorker:\n"
            "    def execute(self):\n"
            "        pass\n", 
            encoding="utf-8"
        )

        localizer = Localizer()
        
        # 2. 測試 BM25 檢索
        results = localizer.locate(
            issue_description="predictor class latency issue in prediction", 
            repo_dir=tmp_path, 
            max_files=1
        )
        
        assert len(results) == 1
        assert results[0][0] == "predictor.py"
        
        # 3. 測試 AST Boost
        results_ast = localizer.locate(
            issue_description="GatewayService handle_request is broken", 
            repo_dir=tmp_path, 
            max_files=1
        )
        assert len(results_ast) == 1
        assert results_ast[0][0] == "gateway.py"

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
