"""C6J: Retry current-file-state reanchor tests.

Ensures retry uses current file state for SEARCH span, not stale locked span.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_semantic_retry_reanchors_from_current_file_state_after_first_attempt_edit():
    """After first attempt modifies file, retry must re-anchor from current file state."""
    from nexus.services.local_heal.canonical_span import get_canonical_search_span

    # Simulate: first attempt modified the file
    current_source = (
        "def normalize_score(score, min_val, max_val):\n"
        "    if max_val == min_val:\n"
        "        return 0.5\n"
        "    return max(0, min(1, (score - min_val) / (max_val - min_val)))\n"
    )

    # The first attempt's patch diff (old code was removed)
    first_attempt_patch = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,5 @@\n"
        " def normalize_score(score, min_val, max_val):\n"
        "-    return (score - min_val) / (max_val - min_val)\n"
        "+    if max_val == min_val:\n"
        "+        return 0.5\n"
        "+    return max(0, min(1, (score - min_val) / (max_val - min_val)))\n"
    )

    # Write current source to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(current_source)
        source_file = Path(f.name)

    try:
        # Get canonical span from the first attempt's patch
        result = get_canonical_search_span(
            locked_search="",
            patch_diff=first_attempt_patch,
            source_file=source_file,
            target_symbol="normalize_score",
            failed_search_text="",
        )

        assert result is not None
        # The span should match the CURRENT file state, not the old code
        assert result.span in current_source, (
            f"Canonical span should match current file state.\n"
            f"Got: {result.span}\n"
            f"Expected substring of: {current_source}"
        )
    finally:
        source_file.unlink()


def test_hash_mismatch_retry_does_not_reuse_stale_locked_search_span():
    """When hash_mismatch occurs, retry must not reuse stale locked_search."""
    from nexus.services.local_heal.canonical_span import get_canonical_search_span

    # Current source has been modified
    current_source = (
        "def normalize_score(score, min_val, max_val):\n"
        "    if max_val == min_val:\n"
        "        return 0.5\n"
        "    return max(0, min(1, (score - min_val) / (max_val - min_val)))\n"
    )

    # Stale locked_search from before first attempt
    stale_locked_search = "def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(current_source)
        source_file = Path(f.name)

    try:
        # When locked_search is provided but stale, AST boundary should win
        result = get_canonical_search_span(
            locked_search=stale_locked_search,
            patch_diff="",
            source_file=source_file,
            target_symbol="normalize_score",
            failed_search_text="",
        )

        assert result is not None
        # If locked_search is stale, AST boundary should extract from current file
        # The span should contain the current code, not the stale code
        if result.source == "locked_search":
            # If locked_search was used, it should match current source
            assert result.span in current_source, (
                f"locked_search span should match current file state"
            )
    finally:
        source_file.unlink()


def test_retry_prompt_canonical_search_span_matches_current_source_text():
    """The canonical_search_span sent to retry prompt must match current source text."""
    from nexus.services.local_heal.canonical_span import get_canonical_search_span

    current_source = (
        "def normalize_score(score, min_val, max_val):\n"
        "    if max_val == min_val:\n"
        "        return 0.5\n"
        "    return max(0, min(1, (score - min_val) / (max_val - min_val)))\n"
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
        # Span must be verbatim substring of current source
        assert result.span.strip() in current_source, (
            f"Canonical span must match current source text"
        )
    finally:
        source_file.unlink()


def test_c15_3v_source_alignment_regression_guard():
    """Guard against C15-3V source alignment regression."""
    from nexus.services.local_heal.canonical_span import get_canonical_search_span

    # Scenario: first attempt changed function signature
    current_source = (
        "def normalize_score(scores):\n"
        "    if not scores:\n"
        "        return []\n"
        "    min_score = min(scores)\n"
        "    max_score = max(scores)\n"
        "    if min_score == max_score:\n"
        "        return [0.5] * len(scores)\n"
        "    return [(s - min_score) / (max_score - min_score) for s in scores]\n"
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
        # Must extract from current source, not from any stale state
        assert result.span.strip() in current_source
    finally:
        source_file.unlink()
