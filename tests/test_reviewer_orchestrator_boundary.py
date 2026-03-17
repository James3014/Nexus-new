import pytest
from unittest.mock import MagicMock
from nexus.services.reviewer import CodexLoopV2

def test_reviewer_is_oneshot():
    # Setup mock dependencies
    mock_git = MagicMock()
    mock_git.project_root = "."
    mock_git.get_changes.return_value = (["test.py"], "diff")
    mock_llm = MagicMock()
    mock_llm.ask.return_value = ({"status": "PASS", "summary": "ok"}, "raw")
    mock_linter = MagicMock()
    
    reviewer = CodexLoopV2(
        project_root=".",
        git=mock_git,
        llm=mock_llm,
        linter=mock_linter
    )
    
    # Review should NOT loop internally if we tell it to behave
    result = reviewer.run_review()
    assert result["status"] == "APPROVED"
    assert mock_llm.ask.call_count == 1
