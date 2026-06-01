import pytest
from pathlib import Path
from nexus.services.local_heal.patcher import Patcher, PatchResult

def test_patcher_syntax_preflight_valid():
    patcher = Patcher()
    content = "def hello():\n    return True\n"
    search = "return True"
    replace = "return False"
    
    # Valid syntax should pass
    res = patcher.apply_patch(content, search, replace, validate_syntax_gate=True)
    assert res.success is True
    assert res.syntax_gate_passed is True
    assert "return False" in res.new_content

def test_patcher_syntax_preflight_invalid():
    patcher = Patcher()
    content = "def hello():\n    return True\n"
    search = "return True"
    replace = "return False (" # Unclosed parenthesis
    
    # Invalid syntax should be intercepted
    res = patcher.apply_patch(content, search, replace, validate_syntax_gate=True)
    assert res.success is False
    assert res.syntax_gate_passed is False
    assert "SYNTAX_ERROR" in res.error_message

def test_patcher_syntax_preflight_whole_file_invalid():
    patcher = Patcher()
    content = "print('old')"
    search = "WHOLE_FILE"
    replace = "print('new' " # Syntax error
    
    res = patcher.apply_patch(content, search, replace, validate_syntax_gate=True)
    assert res.success is False
    assert res.syntax_gate_passed is False
    assert "SYNTAX_ERROR" in res.error_message
