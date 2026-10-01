import pytest
from unittest.mock import MagicMock, patch
from nexus.services.review_strategy import (
    CodeReviewStrategy, 
    ConversationReviewStrategy, 
    ReviewerFactory
)

@pytest.fixture
def mock_reviewer():
    reviewer = MagicMock()
    reviewer.persona_hint = "You are an AI auditor."
    reviewer.task = "Test task"
    reviewer.execution_mode = "developer"
    reviewer.apply_patch = False
    reviewer.scope = "staged"
    reviewer.base_ref = "HEAD"
    
    # 預設回傳
    reviewer._build_review_result.side_effect = lambda status, summary, **kwargs: {
        "status": status, "summary": summary, **kwargs
    }
    reviewer.linter.scan.return_value = {}
    reviewer.llm.ask.return_value = ({"status": "PASS", "summary": "Looks good"}, "raw")
    reviewer.git.get_changes.return_value = ([], "")
    return reviewer

class TestCodeReviewStrategy:
    def test_execute_no_changes(self, mock_reviewer):
        strategy = CodeReviewStrategy()
        mock_reviewer.git.get_changes.return_value = ([], "")
        
        result = strategy.execute(mock_reviewer)
        
        assert result["status"] == "APPROVED"
        assert "No changes found" in result["summary"]

    def test_execute_with_core_file_trigger(self, mock_reviewer):
        strategy = CodeReviewStrategy()
        mock_reviewer.git.get_changes.return_value = (["nexus/core/engine.py"], "diff content")
        
        strategy.execute(mock_reviewer)
        
        mock_reviewer.set_execution_mode.assert_called_with("agent-shield", "P0_core_file_change")

    def test_execute_rejected_by_llm(self, mock_reviewer):
        strategy = CodeReviewStrategy()
        mock_reviewer.git.get_changes.return_value = (["test.py"], "diff")
        mock_reviewer.llm.ask.return_value = ({"status": "FAIL", "summary": "Bug found", "violations": ["line 1"]}, "raw")
        
        result = strategy.execute(mock_reviewer)
        
        assert result["status"] == "RECOVERABLE_BLOCK"
        assert result["retryable"] is True
        assert result["next_action"] == "REVISE"
        assert result["summary"] == "Bug found"

    def test_execute_explicit_rejected_is_terminal_and_not_retryable(self, mock_reviewer):
        strategy = CodeReviewStrategy()
        mock_reviewer.git.get_changes.return_value = (["test.py"], "diff")
        mock_reviewer.llm.ask.return_value = (
            {"status": "REJECTED", "summary": "Owner disposition"}, "raw"
        )

        result = strategy.execute(mock_reviewer)

        assert result["status"] == "REJECTED"
        assert result["retryable"] is False
        assert result["next_action"] == "none"

class TestConversationReviewStrategy:
    def test_execute_skip_level(self, mock_reviewer):
        strategy = ConversationReviewStrategy()
        mock_reviewer.context_hub.make_pre_routing_decision.return_value = {"audit_level": "skip"}
        
        result = strategy.execute(mock_reviewer)
        
        assert result["status"] == "SKIPPED_QUOTA"
        assert mock_reviewer.llm.ask.called is False

    def test_execute_full_audit(self, mock_reviewer):
        strategy = ConversationReviewStrategy()
        mock_reviewer.context_hub.make_pre_routing_decision.return_value = {"audit_level": "full"}
        mock_reviewer.context_hub.assemble_conversation_pack.return_value = {"history": []}
        mock_reviewer.llm.ask.return_value = ({"status": "PASS", "summary": "Logic OK"}, "raw")
        
        result = strategy.execute(mock_reviewer)
        
        assert result["status"] == "APPROVED"
        assert mock_reviewer.llm.ask.called is True

    def test_failed_audit_is_reviseable_not_terminal(self, mock_reviewer):
        strategy = ConversationReviewStrategy()
        mock_reviewer.context_hub.make_pre_routing_decision.return_value = {"audit_level": "full"}
        mock_reviewer.context_hub.assemble_conversation_pack.return_value = {"history": []}
        mock_reviewer.llm.ask.return_value = ({"status": "FAILED", "summary": "retry"}, "raw")

        result = strategy.execute(mock_reviewer)

        assert result["status"] == "RECOVERABLE_BLOCK"
        assert result["retryable"] is True
        assert result["next_action"] == "REVISE"

class TestReviewerFactory:
    def test_create_conversation(self):
        strategy = ReviewerFactory.create("conversation")
        assert isinstance(strategy, ConversationReviewStrategy)

    def test_create_developer(self):
        strategy = ReviewerFactory.create("developer")
        assert isinstance(strategy, CodeReviewStrategy)

    def test_create_unknown_fallback(self):
        strategy = ReviewerFactory.create("invalid_mode")
        assert isinstance(strategy, CodeReviewStrategy)
