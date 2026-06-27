from __future__ import annotations

import os
import tempfile
from nexus.services.local_heal.local_model_source_anchor import build_local_model_source_anchor


def test_build_source_anchor_locked_search() -> None:
    anchor = build_local_model_source_anchor(
        source_root=".",
        target_file="f.py",
        target_symbol="my_fn",
        locked_search="def my_fn():\n    pass",
    )
    assert anchor.canonical_span_source == "locked_search"
    assert anchor.fallback_used is False
    assert anchor.span_hash != ""
    assert anchor.blockers == ()


def test_build_source_anchor_missing() -> None:
    anchor = build_local_model_source_anchor(
        source_root=".",
        target_file="f.py",
        target_symbol="my_fn",
    )
    assert anchor.blockers == ("source_anchor_missing",)
    assert anchor.canonical_span_source == ""


def test_build_source_anchor_ast_fallback() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "code.py"
        src_path = os.path.join(src_root, test_file)
        
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("\n\ndef target_func():\n    return 42\n\n")
            
        anchor = build_local_model_source_anchor(
            source_root=src_root,
            target_file=test_file,
            target_symbol="target_func",
        )
        
        assert anchor.canonical_span_source == "ast_boundary"
        assert anchor.fallback_used is True
        assert anchor.span_start == 3
        assert anchor.span_end == 4
        assert anchor.telemetry["ast_symbol_found"] is True
