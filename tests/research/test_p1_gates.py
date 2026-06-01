import pytest
import random
from pathlib import Path
from nexus.research.selector_rollback import SelectorRollback
from nexus.research.unified_evaluator import UnifiedEvaluator

def test_safe_rollback_logic(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    
    # 建立初始檔案
    core_file = workspace / "core.py"
    core_file.write_text("original_content")
    
    other_file = workspace / "untracked.py"
    other_file.write_text("untracked_content")
    
    selector = SelectorRollback(workspace)
    scope = ["core.py"]
    
    # 1. 備份
    selector.backup_scope("c1", scope)
    
    # 2. 模擬實驗修改
    core_file.write_text("experimental_content")
    other_file.write_text("modified_untracked") # 這不在 scope 內，回滾時不應被恢復 (按設計)
    
    # 3. 回滾
    selector.restore_scope("c1", scope)
    
    # 4. 驗證
    assert core_file.read_text() == "original_content"
    # 設計決策：非 scope 內的檔案不受 restore 影響
    assert other_file.read_text() == "modified_untracked"

def test_reproducible_evaluation():
    evaluator = UnifiedEvaluator(min_score_threshold=0.4)
    
    def mock_test(seed):
        # 故意讓結果依賴隨機種子
        return {"score": random.random(), "cost": 1.0}
    
    report1 = evaluator.evaluate("c1", mock_test)
    report2 = evaluator.evaluate("c2", mock_test)
    
    # 驗證兩次執行相同的種子集會得到完全相同的平均分
    assert report1["average_score"] == report2["average_score"]
    assert report1["seed_details"][0]["score"] == report2["seed_details"][0]["score"]

def test_budget_gate():
    evaluator = UnifiedEvaluator(budget_limit=1.5) # 只能跑零次或一次 (視實作而定)
    
    def mock_test(seed):
        return {"score": 1.0, "cost": 1.0}
        
    report = evaluator.evaluate("c1", mock_test)
    # 預期在開始第一個 seed 前 cost=0.0 < 0.5，執行完後 cost=1.0 >= 0.5，下一個 seed 停止
    assert len(report["seed_details"]) == 1
    assert report["total_cost"] == 1.0
