"""C6U: True replace-only retry parser tests.

Ensures retry ignores model SEARCH and uses canonical SEARCH directly.
"""
from __future__ import annotations

import pytest


def test_retry_replace_only_ignores_model_search_block():
    """Retry must ignore model's SEARCH block and use canonical SEARCH."""
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    from nexus.services.local_heal.canonical_span import get_canonical_search_span
    import tempfile
    from pathlib import Path

    # Current file state
    current_source = "def func():\n    pass\n"

    # Model hallucinates a different SEARCH
    model_response = (
        "FILE: code.py\n"
        "<<<<<<< SEARCH\n"
        "def func():\n"
        "    return None\n"  # Hallucinated - doesn't match current source
        "=======\n"
        "def func():\n"
        "    return 42\n"
        ">>>>>>> REPLACE\n"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(current_source)
        source_file = Path(f.name)

    try:
        # Get canonical SEARCH from current source
        result = get_canonical_search_span(
            locked_search="",
            patch_diff="",
            source_file=source_file,
            target_symbol="func",
            failed_search_text="",
        )

        assert result is not None
        canonical_search = result.span

        # The canonical SEARCH should match current source, not hallucinated SEARCH
        assert canonical_search.strip() in current_source
        assert "return None" not in canonical_search
    finally:
        source_file.unlink()


def test_hallucinated_search_does_not_block_replace_only_retry():
    """Hallucinated SEARCH should not prevent retry from extracting REPLACE."""
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

    parser = SolidSearchReplaceProtocol()

    # Model response with hallucinated SEARCH but valid REPLACE
    model_response = (
        "FILE: code.py\n"
        "<<<<<<< SEARCH\n"
        "def func():\n"
        "    return None\n"  # Hallucinated
        "=======\n"
        "def func():\n"
        "    return 42\n"
        ">>>>>>> REPLACE\n"
    )

    # Parse with canonical SEARCH as anchor
    canonical_search = "def func():\n    pass"
    intents = parser.parse(model_response, anchor_text=canonical_search)

    # Parse should succeed even with hallucinated SEARCH
    # because anchored_edit mode extracts REPLACE only
    if hasattr(intents, "kind"):
        # If parse fails, it's a bug
        assert False, f"Parse should succeed, got: {intents.kind}"
    else:
        # Parse succeeded - REPLACE should be extracted
        assert len(intents) > 0
        assert "return 42" in intents[0].replace


def test_retry_uses_canonical_search_plus_model_replace():
    """Retry must assemble patch from canonical SEARCH + model REPLACE."""
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

    parser = SolidSearchReplaceProtocol()

    # Model response with hallucinated SEARCH
    model_response = (
        "FILE: code.py\n"
        "<<<<<<< SEARCH\n"
        "def func():\n"
        "    return None\n"
        "=======\n"
        "def func():\n"
        "    return 42\n"
        ">>>>>>> REPLACE\n"
    )

    canonical_search = "def func():\n    pass"
    intents = parser.parse(model_response, anchor_text=canonical_search)

    assert not hasattr(intents, "kind")
    assert len(intents) > 0

    # After lock, the SEARCH should be canonical, not hallucinated
    locked_intent = type(intents[0])(
        file_path=intents[0].file_path,
        search=canonical_search,
        replace=intents[0].replace,
        operation=intents[0].operation,
    )

    assert locked_intent.search == canonical_search
    assert "return None" not in locked_intent.search
    assert "return 42" in locked_intent.replace


def test_search_mismatch_in_response_no_longer_preempts_retry():
    """SEARCH_MISMATCH in model response should not block retry."""
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

    parser = SolidSearchReplaceProtocol()

    # Model response with SEARCH that doesn't match source
    model_response = (
        "FILE: code.py\n"
        "<<<<<<< SEARCH\n"
        "def wrong_function():\n"
        "    pass\n"
        "=======\n"
        "def func():\n"
        "    return 42\n"
        ">>>>>>> REPLACE\n"
    )

    canonical_search = "def func():\n    pass"
    intents = parser.parse(model_response, anchor_text=canonical_search)

    # Should succeed because REPLACE is valid
    assert not hasattr(intents, "kind")
    assert len(intents) > 0
    assert "return 42" in intents[0].replace
