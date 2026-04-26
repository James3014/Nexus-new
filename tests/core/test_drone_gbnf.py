import json
import pytest
from unittest.mock import patch, MagicMock
from nexus.core.drone_engine import LocalBonsaiBrain

def test_gbnf_grammar_injection():
    """
    Test that the GBNF grammar strictly constraint 'action' values to
    ['BASH', 'EDIT', 'DONE']. This ensures zero-hallucination action types.
    """
    brain = LocalBonsaiBrain("http://dummy")
    
    with patch("nexus.core.drone_engine.requests.post") as mock_post:
        # Mock successful JSON response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": '{"action": "BASH", "command": "pwd"}'}
        mock_post.return_value = mock_resp
        
        messages = [{"role": "user", "content": "List files"}]
        result = brain.ask_structured(messages)
        
        # Verify grammar is sent in payload
        assert mock_post.called
        call_kwargs = mock_post.call_args.kwargs
        assert "json" in call_kwargs
        payload = call_kwargs["json"]
        
        assert "grammar" in payload
        grammar_str = payload["grammar"]
        
        # Verify the tight constraints are in the grammar
        assert "action_val ::= \"\\\"BASH\\\"\" | \"\\\"EDIT\\\"\" | \"\\\"DONE\\\"\"" in grammar_str
        assert "root   ::= \"{\" space \"\\\"action\\\"\" space \":\" space action_val" in grammar_str
        
        assert result.get("action") == "BASH"
