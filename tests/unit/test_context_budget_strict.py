import pytest
from nexus.services.local_heal.context_budget import ContextBudgetManager, ContextBudgetConfig

def test_budget_rejects_over_budget_context():
    # 500 tokens * 3.5 chars/token = 1750 chars max
    config = ContextBudgetConfig(source_budget_tokens=500, chars_per_token=3.5)
    manager = ContextBudgetManager(config)
    
    # 模擬 5 個檔案，總長度 5 * 1000 = 5000 chars，遠超 1750 chars 限額
    # 假設順序是從高分到低分排序 (高相關度在前面)
    files = [
        ("file1.py", "a" * 1000),
        ("file2.py", "b" * 1000),
        ("file3.py", "c" * 1000),
        ("file4.py", "d" * 1000),
        ("file5.py", "e" * 1000),
    ]
    
    fitted = manager.fit_source_files(files)
    
    # 總長度必須在 budget 之內 (1750)
    total_len = sum(len(content) for _, content in fitted)
    assert total_len <= 1750
    
    # file4, file5 應該被整檔剔除以符合預算，而不是每個都截斷
    assert len(fitted) < 5
    assert any(name == "file4.py" for name, _ in fitted) is False
    assert any(name == "file5.py" for name, _ in fitted) is False


def test_budget_drops_lowest_score_files_first():
    config = ContextBudgetConfig(source_budget_tokens=600, chars_per_token=3.5) # 2100 chars limit
    manager = ContextBudgetManager(config)
    
    files = [
        ("core.py", "x" * 1000),       # 最重要
        ("helper.py", "y" * 1000),     # 次要
        ("unused.py", "z" * 1000),     # 最不重要
    ]
    
    fitted = manager.fit_source_files(files)
    
    # 總長度 ≤ 2100
    assert sum(len(content) for _, content in fitted) <= 2100
    
    # 依序剔除：unused.py 應被剔除；helper.py 應被剔除或截斷；core.py 應完整保留
    filenames = [name for name, _ in fitted]
    assert "unused.py" not in filenames
    assert "core.py" in filenames
    
    # core.py 應該完整保留 1000 chars
    core_content = [content for name, content in fitted if name == "core.py"][0]
    assert len(core_content) == 1000


def test_enforce_hard_limit_enforces_limit():
    config = ContextBudgetConfig(source_budget_tokens=400, chars_per_token=3.5) # 1400 chars limit
    manager = ContextBudgetManager(config)
    
    files = [
        ("file1.py", "a" * 800),
        ("file2.py", "b" * 800),
    ]
    
    # enforce_hard_limit 應該直接處理並限縮
    limited = manager.enforce_hard_limit(files)
    assert sum(len(content) for _, content in limited) <= 1400
    assert len(limited) == 1  # file2 應被剔除
    assert limited[0][0] == "file1.py"
