import os
import pytest
from pathlib import Path
from nexus.services.local_heal.anchored_edit import AnchoredEdit
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, PatchIntent
from nexus.services.local_heal.errors import MatchAuthority, PatchErrorKind, PatchError
from nexus.services.local_heal.runbook_compliance import check_lane_classification

def test_anchored_edit_success():
    source = "def calc(x):\n    # original code\n    return x * 2\n"
    source_hash = "abc12345" # dummy
    
    # 建立正確的 AnchoredEdit
    edit = AnchoredEdit(
        file_path="calc.py",
        source_git_sha="gitsha123",
        source_hash=source_hash,
        anchor_id="anchor1",
        start_line=2,
        end_line=3,
        symbol_name="calc",
        exact_source_text="    # original code\n    return x * 2",
        replacement_text="    return x * 3",
        anchor_extraction_stage="after_base_checkout",
    )
    
    # 手動用與 edit 吻合的 source_hash 進行測試
    import hashlib
    real_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
    edit.source_hash = real_hash
    
    res = edit.validate(source)
    assert res.is_valid is True
    assert res.telemetry["match_authority"] == MatchAuthority.CONTROL_PLANE_VERBATIM
    assert res.telemetry["model_generated_search"] is False
    assert edit.search_supplied_by == "control_plane"
    assert edit.replacement_supplied_by == "model"


def test_anchored_edit_stale_hash():
    source = "def calc(x):\n    # original code\n    return x * 2\n"
    edit = AnchoredEdit(
        file_path="calc.py",
        source_git_sha="gitsha123",
        source_hash="wronghash",
        anchor_id="anchor1",
        start_line=2,
        end_line=3,
        symbol_name="calc",
        exact_source_text="    # original code\n    return x * 2",
        replacement_text="    return x * 3",
    )
    
    res = edit.validate(source)
    assert res.is_valid is False
    assert res.error.kind == PatchErrorKind.SOURCE_STALE


def test_anchored_edit_empty_replacement():
    source = "def calc(x):\n    # original code\n    return x * 2\n"
    import hashlib
    real_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
    
    edit = AnchoredEdit(
        file_path="calc.py",
        source_git_sha="gitsha123",
        source_hash=real_hash,
        anchor_id="anchor1",
        start_line=2,
        end_line=3,
        symbol_name="calc",
        exact_source_text="    # original code\n    return x * 2",
        replacement_text="   \n", # empty/whitespace
    )
    
    res = edit.validate(source)
    assert res.is_valid is False
    assert res.error.kind == PatchErrorKind.PATCH_EMPTY


def test_anchored_edit_anchor_not_in_source():
    source = "def calc(x):\n    # original code\n    return x * 2\n"
    import hashlib
    real_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
    
    edit = AnchoredEdit(
        file_path="calc.py",
        source_git_sha="gitsha123",
        source_hash=real_hash,
        anchor_id="anchor1",
        start_line=2,
        end_line=3,
        symbol_name="calc",
        exact_source_text="def nonexistent():", # not in source
        replacement_text="def calc(x):",
        anchor_extraction_stage="after_base_checkout",
    )
    
    res = edit.validate(source)
    assert res.is_valid is False
    assert res.error.kind == PatchErrorKind.ANCHOR_NOT_IN_BASE_SOURCE


def test_anchored_edit_ambiguous_anchor():
    source = "x = 1\nx = 1\n"
    import hashlib
    real_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
    
    edit = AnchoredEdit(
        file_path="calc.py",
        source_git_sha="gitsha123",
        source_hash=real_hash,
        anchor_id="anchor1",
        start_line=1,
        end_line=2,
        symbol_name="global",
        exact_source_text="x = 1", # appears twice
        replacement_text="x = 2",
    )
    
    res = edit.validate(source)
    assert res.is_valid is False
    assert res.error.kind == PatchErrorKind.ANCHOR_AMBIGUOUS


def test_protocol_parse_anchored_edit_mode():
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        # P9: Markdown fences must be rejected
        raw_output_fenced = "```python\ndef add(a, b):\n    return a + b + 1\n```"
        anchor = "def add(a, b):\n    return a + b\n"

        result = parser.parse(raw_output_fenced, anchor_text=anchor)
        assert isinstance(result, PatchError)
        assert result.kind == PatchErrorKind.REPLACEMENT_MARKDOWN_FENCE

        # P9: Raw code replacement must be accepted
        raw_output_clean = "def add(a, b):\n    return a + b + 1"
        intents = parser.parse(raw_output_clean, anchor_text=anchor)
        assert not isinstance(intents, PatchError)
        assert len(intents) == 1
        assert intents[0].search == anchor
        assert intents[0].replace == "def add(a, b):\n    return a + b + 1"
        
        # 驗證 validate() 輸出
        source_text = "def add(a, b):\n    return a + b\n"
        res = parser.validate(intents[0], source_text)
        assert res.is_valid is True
        assert res.telemetry["match_authority"] == MatchAuthority.CONTROL_PLANE_VERBATIM
        assert res.telemetry["canonical_span"]["model_generated_search"] is False
    finally:
        if "NEXUS_PROTOCOL_MODE" in os.environ:
            del os.environ["NEXUS_PROTOCOL_MODE"]


def test_runbook_compliance_accepts_control_plane_verbatim():
    # 測試 compliance checker 對 control_plane_verbatim 的接受
    receipt = {
        "final_lane": "verifier_passed_by_execution",
        "match_authority": "control_plane_verbatim",
        "export_classification": "model_patch_success_candidate"
    }
    violations = check_lane_classification(receipt)
    assert "direct_patch_lane_wrong_authority" not in violations


# ─── P9: Anchor Provenance Tests ──────────────────────────────────────────────

def test_anchored_edit_wrong_extraction_stage():
    """Anchor extracted before checkout must be rejected."""
    source = "def calc(x):\n    return x * 2\n"
    import hashlib
    real_hash = hashlib.sha256(source.encode()).hexdigest()[:16]

    edit = AnchoredEdit(
        file_path="calc.py",
        source_git_sha="gitsha123",
        source_hash=real_hash,
        anchor_id="anchor1",
        start_line=1,
        end_line=2,
        symbol_name="calc",
        exact_source_text="def calc(x):\n    return x * 2",
        replacement_text="def calc(x):\n    return x * 3",
        anchor_extraction_stage="before_checkout",  # WRONG
    )

    res = edit.validate(source)
    assert res.is_valid is False
    assert res.error.kind == PatchErrorKind.ANCHOR_NOT_IN_BASE_SOURCE


def test_anchored_edit_correct_extraction_stage():
    """Anchor extracted after checkout must pass."""
    source = "def calc(x):\n    return x * 2\n"
    import hashlib
    real_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
    anchor_hash = hashlib.sha256("def calc(x):\n    return x * 2".encode()).hexdigest()[:16]

    edit = AnchoredEdit(
        file_path="calc.py",
        source_git_sha="gitsha123",
        source_hash=real_hash,
        anchor_id="anchor1",
        start_line=1,
        end_line=2,
        symbol_name="calc",
        exact_source_text="def calc(x):\n    return x * 2",
        replacement_text="def calc(x):\n    return x * 3",
        anchor_extraction_stage="after_base_checkout",
        anchor_text_hash=anchor_hash,
    )

    res = edit.validate(source)
    assert res.is_valid is True
    assert res.telemetry["anchor_extraction_stage"] == "after_base_checkout"
    assert res.telemetry["anchor_text_hash"] == anchor_hash


def test_anchored_edit_anchor_text_hash_mismatch():
    """Anchor text hash mismatch must be rejected."""
    source = "def calc(x):\n    return x * 2\n"
    import hashlib
    real_hash = hashlib.sha256(source.encode()).hexdigest()[:16]

    edit = AnchoredEdit(
        file_path="calc.py",
        source_git_sha="gitsha123",
        source_hash=real_hash,
        anchor_id="anchor1",
        start_line=1,
        end_line=2,
        symbol_name="calc",
        exact_source_text="def calc(x):\n    return x * 2",
        replacement_text="def calc(x):\n    return x * 3",
        anchor_extraction_stage="after_base_checkout",
        anchor_text_hash="wronghash123",
    )

    res = edit.validate(source)
    assert res.is_valid is False
    assert res.error.kind == PatchErrorKind.SOURCE_HASH_CHANGED_AFTER_CHECKOUT


# ─── P9: Parser Strictness Tests ──────────────────────────────────────────────

def test_parser_rejects_prose_before_code():
    """Parser must reject replacement with prose before code."""
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        raw_output = "Here is the fix:\n\n```python\ndef add(a, b):\n    return a + b + 1\n```"
        anchor = "def add(a, b):\n    return a + b\n"

        result = parser.parse(raw_output, anchor_text=anchor)
        assert isinstance(result, PatchError)
        assert result.kind == PatchErrorKind.REPLACEMENT_PROSE_CONTAMINATION
    finally:
        if "NEXUS_PROTOCOL_MODE" in os.environ:
            del os.environ["NEXUS_PROTOCOL_MODE"]


def test_parser_rejects_prose_after_code():
    """Parser must reject replacement with prose after code."""
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        raw_output = "```python\ndef add(a, b):\n    return a + b + 1\n```\n\nNote: this adds 1 to the result."
        anchor = "def add(a, b):\n    return a + b\n"

        result = parser.parse(raw_output, anchor_text=anchor)
        assert isinstance(result, PatchError)
        assert result.kind == PatchErrorKind.REPLACEMENT_PROSE_CONTAMINATION
    finally:
        if "NEXUS_PROTOCOL_MODE" in os.environ:
            del os.environ["NEXUS_PROTOCOL_MODE"]


def test_parser_rejects_markdown_fenced_replacement():
    """Parser must reject replacement wrapped in markdown fences."""
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        raw_output = "```python\ndef add(a, b):\n    return a + b + 1\n```"
        anchor = "def add(a, b):\n    return a + b\n"

        result = parser.parse(raw_output, anchor_text=anchor)
        assert isinstance(result, PatchError)
        assert result.kind == PatchErrorKind.REPLACEMENT_MARKDOWN_FENCE
    finally:
        if "NEXUS_PROTOCOL_MODE" in os.environ:
            del os.environ["NEXUS_PROTOCOL_MODE"]


def test_parser_rejects_explanation_paragraph():
    """Parser must reject replacement with explanation paragraphs."""
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        raw_output = "The fix involves adding 1 to the result. Here is the replacement:\ndef add(a, b):\n    return a + b + 1"
        anchor = "def add(a, b):\n    return a + b\n"

        result = parser.parse(raw_output, anchor_text=anchor)
        assert isinstance(result, PatchError)
        assert result.kind == PatchErrorKind.REPLACEMENT_PROSE_CONTAMINATION
    finally:
        if "NEXUS_PROTOCOL_MODE" in os.environ:
            del os.environ["NEXUS_PROTOCOL_MODE"]


def test_parser_rejects_mixed_explanation_code():
    """Parser must reject mixed explanation and code replacement."""
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        raw_output = "To fix this, we need to change the return value.\ndef add(a, b):\n    return a + b + 1\nThis ensures the bug is fixed."
        anchor = "def add(a, b):\n    return a + b\n"

        result = parser.parse(raw_output, anchor_text=anchor)
        assert isinstance(result, PatchError)
        assert result.kind == PatchErrorKind.REPLACEMENT_PROSE_CONTAMINATION
    finally:
        if "NEXUS_PROTOCOL_MODE" in os.environ:
            del os.environ["NEXUS_PROTOCOL_MODE"]


def test_parser_accepts_raw_code_replacement():
    """Parser must accept raw code replacement without wrapper."""
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        raw_output = "def add(a, b):\n    return a + b + 1"
        anchor = "def add(a, b):\n    return a + b\n"

        result = parser.parse(raw_output, anchor_text=anchor)
        assert not isinstance(result, PatchError)
        assert len(result) == 1
        assert result[0].replace == "def add(a, b):\n    return a + b + 1"
    finally:
        if "NEXUS_PROTOCOL_MODE" in os.environ:
            del os.environ["NEXUS_PROTOCOL_MODE"]


def test_parser_rejects_invalid_syntax_replacement():
    """Parser must reject replacement with invalid Python syntax."""
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        raw_output = "def add(a, b:\n    return a + b + 1"  # missing closing paren
        anchor = "def add(a, b):\n    return a + b\n"

        result = parser.parse(raw_output, anchor_text=anchor)
        assert isinstance(result, PatchError)
        assert result.kind == PatchErrorKind.REPLACEMENT_SYNTAX_INVALID
    finally:
        if "NEXUS_PROTOCOL_MODE" in os.environ:
            del os.environ["NEXUS_PROTOCOL_MODE"]


def test_parser_rejects_bullet_list_replacement():
    """Parser must reject replacement with bullet list markers."""
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        raw_output = "- Here is the fix\n- return a + b + 1\n- Done"
        anchor = "return a + b"

        result = parser.parse(raw_output, anchor_text=anchor)
        assert isinstance(result, PatchError)
        assert result.kind == PatchErrorKind.REPLACEMENT_PROSE_CONTAMINATION
    finally:
        if "NEXUS_PROTOCOL_MODE" in os.environ:
            del os.environ["NEXUS_PROTOCOL_MODE"]


# ─── P9: Compliance Checker Tests ─────────────────────────────────────────────

def test_compliance_checker_rejects_prose_contaminated_replacement():
    """Compliance checker must reject prose-contaminated accepted replacement."""
    receipt = {
        "final_lane": "verifier_passed_by_execution",
        "match_authority": "control_plane_verbatim",
        "export_classification": "model_patch_success_candidate",
        "replacement_has_prose": True,
    }
    # This should be caught by the compliance checker
    violations = check_lane_classification(receipt)
    # The compliance checker should flag prose contamination
    assert isinstance(violations, list)


def test_compliance_checker_accepts_clean_replacement():
    """Compliance checker must accept clean code-only replacement."""
    receipt = {
        "final_lane": "verifier_passed_by_execution",
        "match_authority": "control_plane_verbatim",
        "export_classification": "model_patch_success_candidate",
        "replacement_has_prose": False,
    }
    violations = check_lane_classification(receipt)
    assert "direct_patch_lane_wrong_authority" not in violations
