import pytest
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, PatchIntent, SyntaxGate
from nexus.services.local_heal.errors import PatchErrorKind

def test_protocol_parse_valid_block():
    raw = "FILE: test.py\n<<<<<<< SEARCH\nold_code()\n=======\nnew_code()\n>>>>>>> REPLACE"
    protocol = SolidSearchReplaceProtocol()
    intents = protocol.parse(raw)
    assert isinstance(intents, list)
    assert len(intents) == 1
    assert intents[0].file_path == "test.py"
    assert intents[0].search == "old_code()"
    assert intents[0].replace == "new_code()"

def test_protocol_parse_multiple_blocks():
    raw = """
FILE: a.py
<<<<<<< SEARCH
1
=======
2
>>>>>>> REPLACE

FILE: b.py
<<<<<<< SEARCH
X
=======
Y
>>>>>>> REPLACE
"""
    protocol = SolidSearchReplaceProtocol()
    intents = protocol.parse(raw)
    assert len(intents) == 2
    assert intents[0].file_path == "a.py"
    assert intents[1].file_path == "b.py"

def test_protocol_parse_refusal():
    raw = "I'm sorry, as an AI I cannot modify this sensitive file."
    protocol = SolidSearchReplaceProtocol()
    error = protocol.parse(raw)
    assert error.kind == PatchErrorKind.REFUSAL_DETECTED

def test_protocol_parse_empty():
    protocol = SolidSearchReplaceProtocol()
    error = protocol.parse("   \n")
    assert error.kind == PatchErrorKind.EMPTY_RESPONSE

def test_protocol_parse_no_blocks():
    raw = "Here is the fix: change x to y."
    protocol = SolidSearchReplaceProtocol()
    error = protocol.parse(raw)
    assert error.kind == PatchErrorKind.NO_BLOCKS_FOUND

def test_protocol_validate_placeholder_in_search():
    intent = PatchIntent("test.py", "def my_fn():\n    ...", "def my_fn():\n    pass")
    protocol = SolidSearchReplaceProtocol()
    res = protocol.validate(intent, "def my_fn():\n    ...")
    assert not res.is_valid
    assert res.error.kind == PatchErrorKind.SEARCH_HAS_PLACEHOLDER

def test_protocol_validate_placeholder_in_replace():
    intent = PatchIntent("test.py", "pass", "if True:\n    # ... existing code")
    protocol = SolidSearchReplaceProtocol()
    res = protocol.validate(intent, "pass")
    assert not res.is_valid
    assert res.error.kind == PatchErrorKind.SEARCH_HAS_PLACEHOLDER

def test_protocol_validate_verbatim_mismatch():
    intent = PatchIntent("test.py", "wrong_code()", "fixed()")
    protocol = SolidSearchReplaceProtocol()
    res = protocol.validate(intent, "actual_code()")
    assert not res.is_valid
    assert res.error.kind == PatchErrorKind.SEARCH_MISMATCH

def test_syntax_gate_valid_python():
    intent = PatchIntent("test.py", "print(1)", "print(2)")
    source = "print(1)"
    res = SyntaxGate.check(intent, source)
    assert res.is_valid

def test_syntax_gate_invalid_python():
    # 產出一個有語法錯誤的代碼：if 語句缺少冒號
    intent = PatchIntent("test.py", "pass", "if True\n    pass") 
    source = "pass"
    res = SyntaxGate.check(intent, source)
    assert not res.is_valid
    assert res.error.kind == PatchErrorKind.SYNTAX_ERROR
    assert "SyntaxError" in res.error.message
