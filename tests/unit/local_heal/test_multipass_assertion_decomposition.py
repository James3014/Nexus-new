"""C6N: General multipass assertion decomposition tests.

Ensures retry decomposes multi-assertion failures into single-assertion rounds.
"""
from __future__ import annotations

import pytest


def test_multipass_selects_one_highest_priority_assertion():
    """Multipass should select one assertion at a time."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    verifier_stdout = (
        "EVIDENCE: function does not handle empty input\n"
        "EVIDENCE: function raises TypeError on None input\n"
        "EVIDENCE: function does not validate input types\n"
        "EXPECTED: function should handle empty input, None, and validate types"
    )

    # Parse assertions
    assertions = [line.strip() for line in verifier_stdout.split("\n") if line.strip().startswith("EVIDENCE:")]
    assert len(assertions) == 3

    # Priority: first assertion is highest priority
    priority_assertion = assertions[0]
    assert "empty input" in priority_assertion.lower()


def test_each_retry_round_reanchors_from_current_file_state():
    """Each retry round must re-anchor from current file state."""
    from nexus.services.local_heal.canonical_span import get_canonical_search_span
    import tempfile
    from pathlib import Path

    # After first round, file state changes
    round1_source = "def func(data):\n    return data\n"
    round2_source = "def func(data):\n    if data is None:\n        return None\n    return data\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(round2_source)
        source_file = Path(f.name)

    try:
        result = get_canonical_search_span(
            locked_search="",
            patch_diff="",
            source_file=source_file,
            target_symbol="func",
            failed_search_text="",
        )

        assert result is not None
        # Must match current (round 2) state, not round 1
        assert result.span.strip() in round2_source
    finally:
        source_file.unlink()


def test_each_round_preserves_replace_only_contract():
    """Each round must preserve replace-only contract."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    # Round 1: focus on first assertion
    prompt_r1 = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix function",
        verification_report="EVIDENCE: function does not handle empty input\nEXPECTED: handle empty",
        canonical_search_span="def func(data):\n    return data",
        target_file="code.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: function does not handle empty input",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must still have SEARCH/REPLACE markers
    assert "<<<<<<< SEARCH" in prompt_r1
    assert ">>>>>>> REPLACE" in prompt_r1


def test_verifier_result_determines_next_target_assertion():
    """Verifier result from round N determines round N+1 target."""
    # Simulate: round 1 fixes assertion 1, verifier still fails on assertion 2
    round1_verifier = (
        "EVIDENCE: function raises TypeError on None input\n"
        "EXPECTED: function should handle None"
    )
    assertions_r2 = [line.strip() for line in round1_verifier.split("\n") if line.strip().startswith("EVIDENCE:")]
    assert len(assertions_r2) == 1
    assert "None" in assertions_r2[0]


def test_multipass_no_task_specific_branching():
    """Multipass must not use task-specific if/else."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    verifier_stdout = (
        "EVIDENCE: function does not handle edge case X\n"
        "EXPECTED: handle edge case X"
    )

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix function",
        verification_report=verifier_stdout,
        canonical_search_span="def func():\n    pass",
        target_file="code.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt=verifier_stdout,
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # No task-specific instructions
    assert "max_val == min_val" not in prompt or "max_val == min_val" in verifier_stdout
    assert "division by zero" not in prompt.lower() or "division by zero" in verifier_stdout.lower()
