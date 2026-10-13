from nexus.services.local_heal.context_budget import ContextBudgetConfig, ContextBudgetManager


def test_context_budget_dynamic_cutting():
    # fit_source_files keeps earlier files whole and truncates the first file that no longer fits,
    # but only when at least 1000 chars of budget remain (smaller remainders drop the file).
    config = ContextBudgetConfig(
        source_budget_tokens=500, chars_per_token=3.0
    )  # budget max = 1500 chars
    manager = ContextBudgetManager(config)

    files = [
        ("file1.py", "b" * 100),
        ("file2.py", "a" * 2000),
    ]

    fitted = manager.fit_source_files(files)
    # file1 stays intact, file2 is truncated
    assert fitted[0][1] == "b" * 100
    assert "[truncated" in fitted[1][1]
    assert len(fitted[1][1].split("\n")[0]) < 2000


def test_context_budget_drops_file_when_remaining_budget_too_small():
    config = ContextBudgetConfig(
        source_budget_tokens=10, chars_per_token=3.0
    )  # budget max = 30 chars
    manager = ContextBudgetManager(config)

    fitted = manager.fit_source_files([("file1.py", "a" * 50), ("file2.py", "b" * 10)])
    # Below the 1000-char truncation floor the oversized file is dropped; the small one still fits.
    assert fitted == [("file2.py", "b" * 10)]


def test_context_budget_compress_retry():
    manager = ContextBudgetManager()
    prompt = "Original Prompt ⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]\nError content"

    compressed = manager.compress_retry_prompt(prompt, "New Error")
    assert "⚠️ [NEXUS BATTLESUIT HUD" not in compressed
    assert compressed.strip() == "Original Prompt"
