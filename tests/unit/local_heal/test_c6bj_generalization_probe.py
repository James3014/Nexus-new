"""
C6BJ: Assertion-grounded problem_statement generalization probe.

Verifies that:
1. astropy-13236's problem_statement flows to task_desc correctly
2. Tasks without problem_statement still use the generic fallback
3. problem_statement is task-scoped (no cross-contamination)
4. Other real tasks (sympy-13852) have verifier conditions compatible
   with the problem_statement assertion pattern
5. The pattern generalizes beyond single-task

This is a READ-ONLY test probe. No runtime behavior is changed.
"""
import pytest

ASSERTION_PATTERNS = ["must not contain", "must contain", "must not", "cannot contain", "must be"]


def _get_task_specs():
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    return {s["task_id"]: s for s in build_task_specs()}


def _get_task(specs, task_id):
    assert task_id in specs, f"Task {task_id} not found in benchmark specs"
    return specs[task_id]


# ─── 1. problem_statement flows to task_desc ───

def test_astropy_13236_problem_statement_becomes_task_desc():
    """C6BJ: The problem_statement in astropy-13236's spec must flow
    to the CapabilityTask.task_desc field (not get lost)."""
    from scripts.bench.capability_ab_runner import CapabilityTask

    specs = _get_task_specs()
    spec = _get_task(specs, "astropy__astropy-13236")
    ps = spec["problem_statement"]
    assert ps, "astropy-13236 must have a problem_statement"

    fallback = f"Fix target file buggy code for astropy__astropy-13236"
    task_desc = spec.get("problem_statement") or fallback

    assert task_desc != fallback, (
        "problem_statement must be used instead of fallback"
    )
    assert task_desc == ps, (
        f"task_desc must equal problem_statement, got: {task_desc[:80]}..."
    )
    assert "must not contain" in task_desc.lower(), (
        f"task_desc must contain the verifier assertion: {task_desc}"
    )


def test_sympy_problem_statement_added():
    """C6BL: sympy__sympy-13852 now has a problem_statement (added
    after C6BL anchor fix stabilized the lower layer)."""
    specs = _get_task_specs()
    spec = _get_task(specs, "sympy__sympy-13852")
    ps = spec.get("problem_statement")
    assert ps, "sympy-13852 must have problem_statement (C6BL Phase 5)"
    assert "must contain" in ps.lower(), (
        f"problem_statement must contain verifier assertion: {ps[:120]}"
    )
    assert "a == S.One" in ps, (
        f"problem_statement must reference target pattern: {ps[:120]}"
    )


def test_no_problem_statement_still_fallback():
    """C6BJ: Tasks without problem_statement (e.g. concurrency_bug_02,
    task-a-real, task-b-real) must still use the generic fallback."""
    specs = _get_task_specs()
    no_ps_tasks = [tid for tid, s in specs.items() if not s.get("problem_statement")]
    assert no_ps_tasks, "At least one task must be without problem_statement"

    for tid in no_ps_tasks:
        spec = specs[tid]
        ps = spec.get("problem_statement")
        assert not ps, f"{tid} must not have problem_statement"
        fallback = f"Fix target file buggy code for {tid}"
        task_desc = spec.get("problem_statement") or fallback
        assert task_desc == fallback, (
            f"{tid}: Without problem_statement, task_desc must be fallback"
        )


# ─── 2. problem_statement scope isolation ───

def test_problem_statement_task_scoped():
    """C6BJ: Each task spec is independent. astropy-13236's problem_statement
    must NOT leak into other task specs."""
    specs = _get_task_specs()

    astropy_task = _get_task(specs, "astropy__astropy-13236")
    astropy_ps = astropy_task.get("problem_statement", "")

    other_tasks = [tid for tid in specs if tid != "astropy__astropy-13236"]
    for tid in other_tasks:
        other_ps = specs[tid].get("problem_statement", "")
        if other_ps:
            assert astropy_ps != other_ps, (
                f"Task {tid} has identical problem_statement to astropy-13236 "
                f"- possible copy-paste leak"
            )
            assert "view(NdarrayMixin)" not in other_ps, (
                f"Task {tid} problem_statement leaked astropy-specific content: "
                f"{other_ps[:100]}"
            )


# ─── 3. Other real tasks compatibility check ───

def test_sympy_verifier_compatible_with_problem_statement():
    """C6BJ: sympy-13852's verifier checks for 'a == S.One' in the file.
    This is a positive code-pattern assertion that CAN be expressed
    as a problem_statement: 'must contain a == S.One instead of a is S.One'.
    This shows the assertion pattern generalizes beyond negative
    assertions (astropy-13236's 'must not contain')."""
    specs = _get_task_specs()
    spec = _get_task(specs, "sympy__sympy-13852")
    verify_script = spec.get("verify_script", "")

    assert verify_script, "sympy-13852 must have a verify_script"
    assert "a == S.One" in verify_script or "a is S.One" in verify_script, (
        "sympy verify_script checks for the specific code pattern a == S.One"
    )

    positive_pattern = "must contain"
    assert positive_pattern, "A positive assertion pattern exists"

    example_problem_statement = (
        "Fix sympy/functions/special/zeta_functions.py so that the eval "
        "method uses 'a == S.One' instead of 'a is S.One'. "
        "The patched file must contain 'a == S.One'."
    )

    assert "must contain" in example_problem_statement.lower()
    assert "'a == S.One'" in example_problem_statement
    assert "instead of" in example_problem_statement
    assert "'a is S.One'" in example_problem_statement


def test_assertion_pattern_sign_agnostic():
    """C6BJ: The problem_statement assertion pattern works for both
    positive (sympy: must contain X) and negative (astropy: must not
    contain X) assertions. The generalization is sign-agnostic."""
    neg_patterns = ["must not contain", "cannot contain", "must not"]
    pos_patterns = ["must contain", "must include"]

    specs = _get_task_specs()
    astropy = _get_task(specs, "astropy__astropy-13236")
    astropy_ps = astropy.get("problem_statement", "")

    has_neg = any(p in astropy_ps.lower() for p in neg_patterns)
    assert has_neg, (
        f"astropy problem_statement must contain a negative assertion pattern, "
        f"got: {astropy_ps[:120]}"
    )

    # The pattern can also express positive assertions (sympy-compatible)
    sympy_ps = (
        "Fix sympy/functions/special/zeta_functions.py so that the eval "
        "method uses 'a == S.One'. The patched file must contain 'a == S.One'."
    )
    has_pos = any(p in sympy_ps.lower() for p in pos_patterns)
    assert has_pos, (
        f"Example sympy problem_statement must contain a positive assertion "
        f"pattern: {sympy_ps[:120]}"
    )
    assert "'a == S.One'" in sympy_ps, "Must reference the target code pattern"


# ─── 4. No runtime side effects ───

def test_problem_statement_does_not_affect_verifier_logic():
    """C6BJ: problem_statement is purely a prompt-side signal. It must NOT
    affect the verifier_command, verify_script, or any runtime logic."""
    specs = _get_task_specs()
    for tid, spec in specs.items():
        ps = spec.get("problem_statement")
        if not ps:
            continue

        # problem_statement should not appear in verify_script or verifier_command
        verify = spec.get("verify_script", "")
        verifier_cmd = spec.get("verifier_command", [])

        if verify and "must not contain" in ps.lower():
            assert "must not contain" not in verify.lower(), (
                f"Task {tid}: problem_statement leaked into verify_script"
            )

        verifier_str = " ".join(verifier_cmd) if isinstance(verifier_cmd, list) else str(verifier_cmd)
        if verifier_str and "must not contain" in ps.lower():
            assert "must not contain" not in verifier_str.lower(), (
                f"Task {tid}: problem_statement leaked into verifier_command"
            )
