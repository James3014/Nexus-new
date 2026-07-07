"""
C6BE: Multi-line locked_search prompt narrowing tests.

Verifies that:
1. Both prompt sites contain an ANTI-PROSE example (not just anti-backtick)
2. Multi-line locked_search with prose output is STILL rejected by normalizer
3. Multi-line locked_search with valid code-only REPLACE still parses
4. No regression: C6BG backtick + C6BF empty-cleanup guards remain intact
"""
import pytest


# ─── Multi-line locked_search fixture ───

MULTILINE_LOCKED = (
    "        # Structured ndarray gets viewed as a mixin unless already a valid\n"
    "        # mixin class\n"
    "        if (not isinstance(data, Column) and not data_is_mixin\n"
    "                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n"
    "            data = data.view(NdarrayMixin)\n"
    "            data_is_mixin = True\n"
)

MULTILINE_REPLACEMENT = (
    "        # Structured ndarray gets viewed as a mixin unless already a valid\n"
    "        # mixin class\n"
    "        if (not isinstance(data, Column) and not data_is_mixin\n"
    "                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n"
    "            data_is_mixin = True\n"
)


# ─── Contract: prompts must include anti-prose WRONG example ───

def test_committee_prompt_contains_anti_prose_example():
    """C6BE: The anchored_edit prompt in local_committee_candidate_provider must
    include an anti-prose WRONG example (not just the anti-backtick example)."""
    with open(
        "nexus/services/local_heal/local_committee_candidate_provider.py",
        encoding="utf-8",
    ) as f:
        source = f.read()

    assert "No explanations" in source and "No comments" in source and "Code only" in source, (
        "committee prompt must contain anti-explanation instruction: No explanations. No comments. Code only."
    )


def test_direct_prompt_contains_anti_prose_example():
    """C6BE: The anchored_edit prompt in local_model_executor must include
    an anti-prose WRONG example."""
    with open(
        "nexus/services/local_heal/local_model_executor.py",
        encoding="utf-8",
    ) as f:
        source = f.read()

    assert "No explanations" in source and "No comments" in source and "Code only" in source, (
        "executor prompt must contain anti-explanation instruction: No explanations. No comments. Code only."
    )


# ─── RED: multi-line locked_search + prose output must be rejected ───

def test_multiline_prose_contamination_still_rejected():
    """C6BE: Multi-line locked_search with prose explanation before the
    REPLACE block must still produce REPLACEMENT_PROSE_CONTAMINATION."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    from dataclasses import dataclass

    @dataclass
    class _Req:
        repo_root = ""
        target_file = "astropy/table/table.py"

    # Model output: prose explanation INSIDE the REPLACE body — this is
    # the actual C6BD failure pattern (not preamble prose which is ignored)
    prose_output = (
        "<<<<<<< REPLACE\n"
        "# The fix should remove the view(NdarrayMixin) call\n"
        f"{MULTILINE_REPLACEMENT}"
        ">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(_Req(), MULTILINE_LOCKED, prose_output)

    assert meta.get("protocol_parse_failed"), (
        f"Expected protocol_parse_failed=True for prose, got meta={meta}"
    )
    assert "PROSE" in meta.get("error_kind", "").upper(), (
        f"Expected prose contamination error, got {meta.get('error_kind')}"
    )


# ─── GREEN: multi-line locked_search + code-only REPLACE must still parse ───

def test_multiline_code_only_parses():
    """C6BE: Multi-line locked_search with valid code-only REPLACE (no prose,
    no backticks) must still produce a valid unified diff."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    from dataclasses import dataclass

    @dataclass
    class _Req:
        repo_root = ""
        target_file = "astropy/table/table.py"

    # Clean output: REPLACE block only, no prose, no backticks
    clean_output = (
        "<<<<<<< REPLACE\n"
        f"{MULTILINE_REPLACEMENT}"
        ">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(_Req(), MULTILINE_LOCKED, clean_output)

    assert not meta.get("protocol_parse_failed"), (
        f"Expected parse to succeed for code-only REPLACE, got meta={meta}"
    )
    assert "--- a/" in patch, (
        f"Expected unified diff, got:\n{patch[:200]}"
    )


# ─── Regression: C6BG backtick-wrapped + valid replacement still works ───

def test_multiline_fence_unwrapped_still_works():
    """C6BE: Multi-line locked_search with fence-unwrapped content must
    still produce a valid diff (C6BG regression guard)."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    from dataclasses import dataclass

    @dataclass
    class _Req:
        repo_root = ""
        target_file = "astropy/table/table.py"

    fenced_output = (
        "```\n"
        "<<<<<<< REPLACE\n"
        f"{MULTILINE_REPLACEMENT}"
        ">>>>>>> REPLACE\n"
        "```"
    )

    patch, meta = _normalize_candidate_patch(_Req(), MULTILINE_LOCKED, fenced_output)

    assert not meta.get("protocol_parse_failed"), (
        f"Expected fence-unwrap to succeed, got meta={meta}"
    )
    assert "--- a/" in patch, (
        f"Expected unified diff, got:\n{patch[:200]}"
    )


# ─── Regression: C6BF EMPTY_AFTER_CLEANUP still detected ───

def test_multiline_identical_replacement_still_empty():
    """C6BE: Multi-line locked_search with identical replacement must still
    produce EMPTY_AFTER_CLEANUP (C6BF regression guard)."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    from dataclasses import dataclass

    @dataclass
    class _Req:
        repo_root = ""
        target_file = "astropy/table/table.py"

    identical_output = (
        "<<<<<<< REPLACE\n"
        f"{MULTILINE_LOCKED}"
        ">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(_Req(), MULTILINE_LOCKED, identical_output)

    assert meta.get("protocol_parse_failed"), (
        f"Expected protocol_parse_failed=True, got meta={meta}"
    )
    assert meta.get("error_kind") == "EMPTY_AFTER_CLEANUP", (
        f"Expected EMPTY_AFTER_CLEANUP, got {meta.get('error_kind')}"
    )


# ─── C6BF: assertion-grounded problem_statement contract ───

def test_13236_benchmark_spec_has_assertion_grounded_problem_statement():
    """C6BF: The astropy__astropy-13236 benchmark spec must include a
    problem_statement that grounds the verifier assertion, not fall back
    to the generic 'Fix target file buggy code'."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs

    specs = build_task_specs()
    task = next(s for s in specs if s["task_id"] == "astropy__astropy-13236")
    ps = task.get("problem_statement", "")

    assert ps, (
        "astropy-13236 must have a non-empty problem_statement (not fallback)"
    )
    assert "view(NdarrayMixin)" in ps, (
        "problem_statement must mention view(NdarrayMixin) so the model knows what to fix"
    )
    assert "not contain" in ps.lower() or "must not" in ps.lower() or "cannot" in ps.lower(), (
        "problem_statement must state the verifier PASS condition (what should NOT be in the file)"
    )


def test_13236_benchmark_spec_has_verifier_condition():
    """C6BF: The problem_statement must explicitly state the verifier's
    pass/fail condition (what the patched file must or must not contain)."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs

    specs = build_task_specs()
    task = next(s for s in specs if s["task_id"] == "astropy__astropy-13236")
    ps = task.get("problem_statement", "")

    assert "must not" in ps.lower(), (
        "problem_statement must contain 'must not' to express the verifier condition"
    )
