"""
C6BG: Prompt-side syntax contract tightening tests.
Verifies that:
1. Both prompt construction sites include the anti-pattern example
2. Normalizer still correctly rejects truly malformed replacement body
3. Regression: fence-unwrapped + valid replacement still produces valid diff
"""
import pytest


# ─── Contract tests: prompt contains anti-pattern ───

def test_committee_prompt_contains_no_backticks_instruction():
    """C6BG: The anchored_edit prompt in local_committee_candidate_provider must
    instruct the model NOT to use backticks."""
    with open(
        "nexus/services/local_heal/local_committee_candidate_provider.py",
        encoding="utf-8",
    ) as f:
        source = f.read()

    assert "WRONG" in source and "will be REJECTED" in source, (
        "committee_candidate_provider must contain WRONG format anti-pattern"
    )
    assert "No backticks" in source, (
        "committee_candidate_provider must contain backtick instruction"
    )


def test_direct_prompt_contains_anti_pattern():
    """C6BG: The anchored_edit prompt in local_model_executor must include an
    explicit anti-pattern (WRONG format) example."""
    with open(
        "nexus/services/local_heal/local_model_executor.py", encoding="utf-8"
    ) as f:
        source = f.read()

    assert "WRONG" in source and "will be REJECTED" in source, (
        "local_model_executor.py must contain WRONG format anti-pattern in anchored_edit prompt"
    )
    assert "No backticks" in source, (
        "local_model_executor.py must contain backtick instruction"
    )


# ─── RED test: REPLACEMENT_SYNTAX_INVALID still fires for broken replacement ───

def test_replacement_syntax_invalid_still_rejected():
    """C6BG: Malformed replacement body must still produce
    REPLACEMENT_SYNTAX_INVALID (regression guard)."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    from dataclasses import dataclass

    @dataclass
    class _Req:
        repo_root = ""
        target_file = "astropy/table/table.py"

    locked_search = "from .ndarray_mixin import NdarrayMixin  # noqa: F401"

    # Model outputs REPLACE block with broken Python in replacement body
    broken_output = (
        "<<<<<<< REPLACE\n"
        "from .ndarray_mixin import NdarrayMixin  # noqa: F401\n"
        "class Incomplete\n"  # invalid: class without body
        ">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(_Req(), locked_search, broken_output)

    assert meta.get("protocol_parse_failed"), (
        f"Expected protocol_parse_failed=True, got meta={meta}"
    )
    error_kind = meta.get("error_kind", "")
    assert error_kind == "REPLACEMENT_SYNTAX_INVALID", (
        f"Expected REPLACEMENT_SYNTAX_INVALID, got {error_kind}"
    )


# ─── GREEN test: fence-unwrapped + valid replacement still works ───

def test_fence_unwrapped_valid_replacement_still_works():
    """C6BG: Fence-unwrapped content with valid replacement must still produce
    a valid diff."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    from dataclasses import dataclass

    @dataclass
    class _Req:
        repo_root = ""
        target_file = "astropy/table/table.py"

    locked_search = "from .ndarray_mixin import NdarrayMixin  # noqa: F401"

    # Model output: fences around REPLACE block with valid replacement
    fenced_output = (
        "```\n"
        "<<<<<<< REPLACE\n"
        "from .ndarray_mixin import NdarrayMixin\n"
        ">>>>>>> REPLACE\n"
        "```"
    )

    patch, meta = _normalize_candidate_patch(_Req(), locked_search, fenced_output)

    assert not meta.get("protocol_parse_failed"), (
        f"Expected parse to succeed (fence unwrapped), got meta={meta}"
    )
    assert "--- a/" in patch, (
        f"Expected unified diff, got:\n{patch[:200]}"
    )


# ─── Regression: prose contamination still rejected ───

def test_prose_contamination_still_rejected():
    """C6BG: Fence-unwrapped content with prose must still produce
    REPLACEMENT_PROSE_CONTAMINATION."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    from dataclasses import dataclass

    @dataclass
    class _Req:
        repo_root = ""
        target_file = "astropy/table/table.py"

    locked_search = "from .ndarray_mixin import NdarrayMixin  # noqa: F401"

    # Model output: fences with explanation + code
    prose_output = (
        "```\n"
        "# Here is the fix: remove the NdarrayMixin import\n"
        "from .ndarray_mixin import NdarrayMixin  # noqa: F401\n"
        "```"
    )

    patch, meta = _normalize_candidate_patch(_Req(), locked_search, prose_output)

    assert meta.get("protocol_parse_failed"), (
        f"Expected protocol_parse_failed=True for prose, got meta={meta}"
    )
    assert "PROSE" in meta.get("error_kind", "").upper(), (
        f"Expected prose contamination error, got {meta.get('error_kind')}"
    )


# ─── Regression: C6BF EMPTY_AFTER_CLEANUP still detected ───

def test_identical_replacement_still_empty_after_cleanup():
    """C6BG: Identical replacement must still produce EMPTY_AFTER_CLEANUP
    (C6BF regression guard)."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    from dataclasses import dataclass

    @dataclass
    class _Req:
        repo_root = ""
        target_file = "astropy/table/table.py"

    locked_search = "from .ndarray_mixin import NdarrayMixin  # noqa: F401"

    identical_output = (
        "<<<<<<< REPLACE\n"
        f"{locked_search}\n"
        ">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(_Req(), locked_search, identical_output)

    assert meta.get("protocol_parse_failed"), (
        f"Expected protocol_parse_failed=True, got meta={meta}"
    )
    assert meta.get("error_kind") == "EMPTY_AFTER_CLEANUP", (
        f"Expected EMPTY_AFTER_CLEANUP, got {meta.get('error_kind')}"
    )
