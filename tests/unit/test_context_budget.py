import pytest
from nexus.services.local_heal.context_budget import ContextBudgetManager, ContextBudgetConfig

def test_context_budget_dynamic_cutting():
    config = ContextBudgetConfig(source_budget_tokens=10, chars_per_token=3.0) # budget max = 30 chars
    manager = ContextBudgetManager(config)
    
    files = [
        ("file1.py", "a" * 50),
        ("file2.py", "b" * 10)
    ]
    
    fitted = manager.fit_source_files(files)
    # file1 應該要被剪裁，file2 保持原樣
    assert "[truncated" in fitted[0][1]
    assert len(fitted[0][1].split("\n")[0]) < 50
    assert fitted[1][1] == "b" * 10

def test_context_budget_compress_retry():
    manager = ContextBudgetManager()
    prompt = "Original Prompt ⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]\nError content"
    
    compressed = manager.compress_retry_prompt(prompt, "New Error")
    assert "⚠️ [NEXUS BATTLESUIT HUD" not in compressed
    assert compressed.strip() == "Original Prompt"
