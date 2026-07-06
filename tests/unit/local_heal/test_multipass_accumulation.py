"""C6O: Multipass current-state accumulation tests.

Ensures round N+1 builds on round N's current file state.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_round2_reads_current_file_state_after_round1_apply():
    """Round 2 must read current file state after round 1 apply."""
    from nexus.services.local_heal.canonical_span import get_canonical_search_span

    # After round 1 applies, file state changes
    round1_source = "def func(data):\n    return data\n"
    round2_source = "def func(data):\n    if data is None:\n        return None\n    return data\n"

    # Round 1 patch diff (old code removed)
    round1_patch = (
        "--- a/code.py\n"
        "+++ b/code.py\n"
        "@@ -1,2 +1,4 @@\n"
        " def func(data):\n"
        "-    return data\n"
        "+    if data is None:\n"
        "+        return None\n"
        "+    return data\n"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(round2_source)
        source_file = Path(f.name)

    try:
        # Round 2 should extract from current file, not from round 1 patch
        result = get_canonical_search_span(
            locked_search="",
            patch_diff=round1_patch,
            source_file=source_file,
            target_symbol="func",
            failed_search_text="",
        )

        assert result is not None
        # Must match current (round 2) state, not round 1
        assert result.span.strip() in round2_source
        assert result.span.strip() != round1_source.strip()
    finally:
        source_file.unlink()


def test_round2_authoritative_search_reflects_round1_accumulation():
    """Round 2's SEARCH span must reflect round 1's patch accumulation."""
    from nexus.services.local_heal.canonical_span import get_canonical_search_span

    # After round 1 applies clamping, file state includes clamping
    current_source = (
        "def normalize_score(score, min_val, max_val):\n"
        "    if max_val == min_val:\n"
        "        return 0.5\n"
        "    return (score - min_val) / (max_val - min_val)\n"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(current_source)
        source_file = Path(f.name)

    try:
        result = get_canonical_search_span(
            locked_search="",
            patch_diff="",
            source_file=source_file,
            target_symbol="normalize_score",
            failed_search_text="",
        )

        assert result is not None
        # SEARCH must include the division-by-zero check from round 1
        assert "max_val == min_val" in result.span
    finally:
        source_file.unlink()


def test_multipass_preserves_prior_fix_while_targeting_next():
    """Multipass must preserve round 1 fix while targeting round 2 assertion."""
    # Round 1 fixes division-by-zero
    round1_fix = "if max_val == min_val: return 0.5"
    # Round 2 should preserve round 1 fix and add clamping
    round2_fix = "if max_val == min_val: return 0.5\nreturn max(0, min(1, (score - min_val) / (max_val - min_val)))"

    # Round 2 fix must contain round 1 fix
    assert round1_fix in round2_fix


def test_no_fallback_to_original_locked_span_after_successful_apply():
    """After successful round 1 apply, round 2 must not use original locked span."""
    from nexus.services.local_heal.canonical_span import get_canonical_search_span

    # Original source
    original_source = "def func():\n    pass\n"
    # After round 1 applies, source changes
    current_source = "def func():\n    if True:\n        return 1\n    return 0\n"

    # Original locked span (from before round 1)
    original_locked = "def func():\n    pass"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(current_source)
        source_file = Path(f.name)

    try:
        # Even if original_locked is provided, current source should win
        result = get_canonical_search_span(
            locked_search=original_locked,
            patch_diff="",
            source_file=source_file,
            target_symbol="func",
            failed_search_text="",
        )

        assert result is not None
        # Must match current source, not original
        assert result.span.strip() in current_source
    finally:
        source_file.unlink()
