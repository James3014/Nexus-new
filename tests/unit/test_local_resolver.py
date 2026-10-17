import importlib.util
import tempfile
from pathlib import Path

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

def test_sandbox_executor_runs_test_and_summarizes() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.sandbox") is None

def test_patch_evaluator_decides_rollback_on_failed_attempts() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.evaluator") is None
