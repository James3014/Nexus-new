import pytest
from unittest.mock import MagicMock
from nexus.services.reviewer import CodexLoopV2

def test_reviewer_is_oneshot_even_on_failure():
    mock_git = MagicMock()
    mock_git.project_root = "."
    mock_git.get_changes.return_value = (["test.py"], "diff")
    mock_llm = MagicMock()
    # Return REJECTED
    mock_llm.ask.return_value = ({"status": "REJECTED", "summary": "fail"}, "raw")
    mock_linter = MagicMock()
    mock_patcher = MagicMock()
    
    reviewer = CodexLoopV2(
        project_root=".",
        git=mock_git,
        llm=mock_llm,
        linter=mock_linter,
        patcher=mock_patcher,
        apply_patch=True # This normally causes looping in the old implementation
    )
    
    result = reviewer.run_review()
    assert result["status"] == "REJECTED"
    # Even with apply_patch=True, the Reviewer component should be one-shot in v9
    assert mock_llm.ask.call_count == 1
