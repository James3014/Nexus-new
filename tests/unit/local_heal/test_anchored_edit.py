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
    )
    
    res = edit.validate(source)
    assert res.is_valid is False
    assert res.error.kind == PatchErrorKind.SEARCH_MISMATCH


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
    assert res.error.kind == PatchErrorKind.NAME_SANITY_ERROR


def test_protocol_parse_anchored_edit_mode():
    parser = SolidSearchReplaceProtocol()
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        # 1. 模型僅回覆了 replacement 代碼本身，甚至帶有 markdown backticks
        raw_output = "```python\ndef add(a, b):\n    return a + b + 1\n```"
        anchor = "def add(a, b):\n    return a + b\n"
        
        intents = parser.parse(raw_output, anchor_text=anchor)
        assert not isinstance(intents, PatchError)
        assert len(intents) == 1
        assert intents[0].search == anchor
        assert intents[0].replace == "def add(a, b):\n    return a + b + 1"
        
        # 2. 驗證 validate() 輸出
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
