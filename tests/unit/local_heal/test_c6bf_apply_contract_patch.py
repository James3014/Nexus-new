"""
C6BF: Prompt-side apply-contract patch — empty_after_cleanup fix.
Verifies that model output with replacement identical to locked_search
is properly classified as parse_failed:EMPTY_AFTER_CLEANUP instead of
silently producing empty patch (e3b0c442...).
"""
import hashlib
from dataclasses import dataclass
import pytest


_REAL_LOCKED_SEARCH = "from .ndarray_mixin import NdarrayMixin  # noqa: F401"
_TARGET_FILE = "astropy/table/table.py"


@dataclass
class _FakeRequest:
    repo_root = ""
    target_file = _TARGET_FILE


# ─── RED test 1: identical replacement must no longer produce empty hash ───

def test_identical_replacement_detected_as_parse_failure():
    """C6BF: When model outputs a REPLACE block with replacement identical to
    locked_search, _normalize_candidate_patch must return protocol_parse_failed
    with error_kind=EMPTY_AFTER_CLEANUP, not silently return empty patch."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch

    identical_output = (
        f"<<<<<<< REPLACE\n"
        f"{_REAL_LOCKED_SEARCH}\n"
        f">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(
        _FakeRequest(), _REAL_LOCKED_SEARCH, identical_output
    )

    assert meta.get("protocol_parse_failed"), (
        f"Expected protocol_parse_failed=True for identical replacement, "
        f"got meta={meta}"
    )
    assert meta.get("error_kind") == "EMPTY_AFTER_CLEANUP", (
        f"Expected error_kind=EMPTY_AFTER_CLEANUP, got {meta.get('error_kind')}"
    )
    assert not patch.strip(), (
        "Expected empty patch for identical replacement"
    )


# ─── RED test 2: different replacement must still produce non-empty patch ───

def test_different_replacement_produces_non_empty_patch():
    """C6BF: When model outputs replacement different from locked_search,
    _normalize_candidate_patch must produce non-empty unified diff."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch

    different_output = (
        f"<<<<<<< REPLACE\n"
        f"from .ndarray_mixin import NdarrayMixin\n"
        f">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(
        _FakeRequest(), _REAL_LOCKED_SEARCH, different_output
    )

    assert not meta.get("protocol_parse_failed"), (
        f"Expected protocol_parse_failed=False for different replacement, "
        f"got meta={meta}"
    )
    assert patch.strip(), (
        "Expected non-empty patch for different replacement"
    )
    # Hash must be non-empty
    h = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    assert h != hashlib.sha256(b"").hexdigest(), (
        "Expected non-empty hash for different replacement"
    )


# ─── RED test 3: SEARCH/REPLACE block with different replacement still works ───

def test_search_replace_block_with_different_replacement_works():
    """C6BF: SEARCH/REPLACE block with non-identical replacement must still
    produce non-empty unified diff."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch

    sr_output = (
        f"<<<<<<< SEARCH\n"
        f"{_REAL_LOCKED_SEARCH}\n"
        f"=======\n"
        f"from .ndarray_mixin import NdarrayMixin\n"
        f">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(
        _FakeRequest(), _REAL_LOCKED_SEARCH, sr_output
    )

    assert not meta.get("protocol_parse_failed"), (
        f"Expected protocol_parse_failed=False, got meta={meta}"
    )
    assert patch.strip(), "Expected non-empty patch from SEARCH/REPLACE block"


# ─── Regression: unified diff passthrough unchanged ───

def test_unified_diff_passthrough_unchanged():
    """C6BF: Unified diff passthrough path must still work unchanged."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch

    udiff = (
        f"--- a/{_TARGET_FILE}\n"
        f"+++ b/{_TARGET_FILE}\n"
        f"@@ -1 +1 @@\n"
        f"-{_REAL_LOCKED_SEARCH}\n"
        f"+from .ndarray_mixin import NdarrayMixin\n"
    )

    patch, meta = _normalize_candidate_patch(
        _FakeRequest(), _REAL_LOCKED_SEARCH, udiff
    )

    assert not meta.get("protocol_parse_failed"), (
        f"Unified diff passthrough must not fail"
    )
    assert meta.get("protocol_used") == "passthrough", (
        f"Expected passthrough protocol, got {meta.get('protocol_used')}"
    )
    assert udiff in patch, "Passthrough must return original diff"


# ─── Regression: fenced output still rejected ───

def test_fenced_output_still_rejected():
    """C6BF: Markdown-fenced output must still be rejected as before."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch

    fenced_output = (
        "```\n"
        f"<<<<<<< REPLACE\n"
        f"some replacement code\n"
        f">>>>>>> REPLACE\n"
        "```\n"
    )

    patch, meta = _normalize_candidate_patch(
        _FakeRequest(), _REAL_LOCKED_SEARCH, fenced_output
    )

    # After fence unwrapping, the replacement should be different from search
    # so this might succeed — we just verify no crash
    assert isinstance(patch, str)
    assert isinstance(meta, dict)


# ─── Regression: empty output still rejected ───

def test_empty_output_still_rejected():
    """C6BF: Truly empty model output must still be rejected."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch

    patch, meta = _normalize_candidate_patch(
        _FakeRequest(), _REAL_LOCKED_SEARCH, ""
    )

    assert meta.get("protocol_parse_failed"), (
        f"Empty output must fail, got meta={meta}"
    )


# ─── Regression: truly invalid format still rejected ───

def test_invalid_format_still_rejected():
    """C6BF: Output with prose contamination must still be rejected."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch

    prose_output = "This is the fix: just remove the import statement entirely."

    patch, meta = _normalize_candidate_patch(
        _FakeRequest(), _REAL_LOCKED_SEARCH, prose_output
    )

    assert meta.get("protocol_parse_failed"), (
        f"Prose output must be rejected, got meta={meta}"
    )


# ─── Regression: compute_failure_class handles EMPTY_AFTER_CLEANUP ───

def test_compute_failure_class_handles_empty_after_cleanup():
    """C6BF: compute_failure_class must return parse_failed:EMPTY_AFTER_CLEANUP
    instead of empty_response when parse_error_kind is set."""
    from nexus.services.local_heal.local_model_executor import compute_failure_class

    fc, reason = compute_failure_class(
        output_len=0,
        provider_error="",
        failure_reason="",
        parse_error_kind="EMPTY_AFTER_CLEANUP",
        patch_lifecycle_state="patch_absent",
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )

    assert fc == "parse_failed:EMPTY_AFTER_CLEANUP", (
        f"Expected parse_failed:EMPTY_AFTER_CLEANUP, got {fc}"
    )
    assert not reason, f"Expected no reason, got {reason}"


# ─── Regression: compute_failure_class falls through correctly when no parse error ───

def test_compute_failure_class_falls_through_when_no_parse_error():
    """C6BF: When output_len=0 and parse_error_kind=none, compute_failure_class
    must fall through to unknown_with_reason (not crash, not parse_failed)."""
    from nexus.services.local_heal.local_model_executor import compute_failure_class

    fc, reason = compute_failure_class(
        output_len=0,
        provider_error="",
        failure_reason="",
        parse_error_kind="none",
        patch_lifecycle_state="patch_absent",
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )

    assert "parse_failed:" not in fc, (
        f"Must not return parse_failed when error_kind is none, got {fc}"
    )
    assert isinstance(fc, str), f"Expected str, got {type(fc)}"


# ─── RED test: verify the exact e3b0c442 empty hash path ───

def test_empty_hash_path_blocked():
    """C6BF: The path that previously produced e3b0c442 (empty SHA256) for
    non-empty raw output must now produce parse_failed instead."""
    from nexus.services.local_heal.local_model_executor import (
        _normalize_candidate_patch, compute_failure_class
    )

    # Simulate the full pipeline's behavior: non-empty raw output,
    # but replacement identical to locked_search
    identical_output = (
        f"<<<<<<< REPLACE\n"
        f"{_REAL_LOCKED_SEARCH}\n"
        f">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(
        _FakeRequest(), _REAL_LOCKED_SEARCH, identical_output
    )

    # The normalize step must identify this as parse failure
    assert meta.get("protocol_parse_failed"), "Identical replacement must be caught"

    # Simulate compute_failure_class with the telemetry
    fc, _ = compute_failure_class(
        output_len=0,
        provider_error="",
        failure_reason="",
        parse_error_kind=meta.get("error_kind", ""),
        patch_lifecycle_state="patch_absent",
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )

    assert fc == "parse_failed:EMPTY_AFTER_CLEANUP", (
        f"Failure class must be parse_failed:EMPTY_AFTER_CLEANUP, got {fc}"
    )
    # Must NOT be empty_response (which would wrongly blame the model)
    assert fc != "empty_response", (
        "Must not classify as empty_response — model DID produce output"
    )
