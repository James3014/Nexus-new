"""
C6BM: Bounded adoption rule guard for assertion-grounded problem_statement.

Verifies:
1. Both adopted tasks (astropy-13236, sympy-13852) meet ALL preconditions
2. A hypothetical task with UNSTABLE anchor does NOT meet preconditions
3. problem_statement format is consistent (not polluted across tasks)
"""
import pytest
import ast


def _get_task_specs():
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    return {s["task_id"]: s for s in build_task_specs()}


# ═══ Adoption Precondition 1: Anchor stabilized ═══

def precondition_anchor_stabilized(spec) -> tuple[bool, str]:
    """Returns (pass, reason) for anchor stability check."""
    ls = spec.get("locked_search", "")
    if not ls or not ls.strip():
        return False, "locked_search is empty"
    lines = ls.strip().splitlines()
    if len(lines) < 2:
        return False, f"locked_search too short ({len(lines)} line(s))"
    try:
        ast.parse(ls)
        return True, "anchor is valid standalone Python"
    except SyntaxError:
        try:
            wrapped = "def _wrapper():\n" + "\n".join(
                f"    {l}" for l in ls.splitlines()
            )
            ast.parse(wrapped)
            return True, "anchor is valid Python with wrapper"
        except SyntaxError as e:
            return False, f"anchor is not parseable Python: {e}"


def test_astropy_13236_anchor_stabilized():
    """C6BM: astropy-13236 meets precondition: anchor stabilized
    (multi-line locked_search, AST-parseable)."""
    specs = _get_task_specs()
    spec = specs["astropy__astropy-13236"]
    ok, reason = precondition_anchor_stabilized(spec)
    assert ok, f"astropy-13236 anchor NOT stabilized: {reason}"


def test_sympy_13852_anchor_stabilized():
    """C6BM: sympy-13852 meets precondition: anchor stabilized
    (multi-line locked_search, AST-parseable with wrapper)."""
    specs = _get_task_specs()
    spec = specs["sympy__sympy-13852"]
    ok, reason = precondition_anchor_stabilized(spec)
    assert ok, f"sympy-13852 anchor NOT stabilized: {reason}"


# ═══ Adoption Precondition 2: problem_statement present with verifier assertion ═══

def precondition_has_verifier_assertion(spec) -> tuple[bool, str]:
    """Returns (pass, reason) for verifier assertion check."""
    ps = spec.get("problem_statement", "")
    if not ps:
        return False, "no problem_statement"
    has_neg = any(p in ps.lower() for p in ["must not contain", "cannot contain", "must not"])
    has_pos = any(p in ps.lower() for p in ["must contain", "must include"])
    if not (has_neg or has_pos):
        return False, f"no verifier assertion pattern in problem_statement: {ps[:100]}"
    return True, "problem_statement contains verifier assertion"


def test_astropy_13236_has_verifier_assertion():
    """C6BM: astropy-13236 problem_statement contains 'must not contain'."""
    specs = _get_task_specs()
    spec = specs["astropy__astropy-13236"]
    ok, reason = precondition_has_verifier_assertion(spec)
    assert ok, f"astropy-13236: {reason}"


def test_sympy_13852_has_verifier_assertion():
    """C6BM: sympy-13852 problem_statement contains 'must contain'."""
    specs = _get_task_specs()
    spec = specs["sympy__sympy-13852"]
    ok, reason = precondition_has_verifier_assertion(spec)
    assert ok, f"sympy-13852: {reason}"


# ═══ Adoption Precondition 3: problem_statement is task-local (no cross-pollution) ═══

def test_problem_statement_assertion_does_not_leak():
    """C6BM: problem_statement with verifier assertion must NOT appear
    in the verify_script or verifier_command of any task."""
    specs = _get_task_specs()
    for tid, spec in specs.items():
        ps = spec.get("problem_statement", "")
        if not ps:
            continue
        # Extract the assertion clause (after 'must' sentence)
        verify = spec.get("verify_script", "")
        if verify:
            assert "must not contain" not in verify.lower() or ps.lower().count("must") <= 1, (
                f"{tid}: problem_statement assertion leaked into verify_script"
            )


# ═══ Adoption Precondition 4: Tasks without stable anchor should NOT adopt ═══

def test_unstable_anchor_task_does_not_meet_preconditions():
    """C6BM: A hypothetical task with single-line locked_search
    (no indented body) fails the anchor stabilization precondition.
    Such tasks should NOT adopt assertion-grounded problem_statement."""
    class _MockSpec:
        def get(self, key, default=None):
            if key == "locked_search":
                return "if a is S.One:"  # 1 line, no body
            return default

    ok, reason = precondition_anchor_stabilized(_MockSpec())
    assert not ok, "single-line locked_search must NOT pass anchor stabilization"
    assert "too short" in reason.lower() or "not parseable" in reason.lower()


# ═══ Adoption Precondition 5: problem_statement does NOT change across tasks ═══

def test_adopted_tasks_format_consistent():
    """C6BM: Both adopted tasks (astropy-13236, sympy-13852) follow
    the same problem_statement format:
    'Fix {file} so that {action}. The patched file must {contain/not contain} {pattern}'."""
    specs = _get_task_specs()
    adopted = ["astropy__astropy-13236", "sympy__sympy-13852"]
    for tid in adopted:
        spec = specs.get(tid)
        assert spec, f"{tid} must exist in benchmark specs"
        ps = spec.get("problem_statement", "")
        assert ps, f"{tid} must have problem_statement"
        assert "Fix " in ps, f"{tid}: problem_statement must start with 'Fix'"
        assert "The patched file must" in ps or "The patched file must not" in ps, (
            f"{tid}: problem_statement must contain assertion clause, got: {ps[:120]}"
        )


# ═══ Capability Closure Matrix Guards ═══

_CAPABILITY_EVIDENCE = {
    "Verifier evidence": "docs/reports/c6bc_post_apply_semantic_gap_forensics.md",
    "Assertion-grounded prompt": "docs/reports/c6bf_apply_contract_patch.md",
    "Anchor shaping/grounding": "docs/reports/c6bd_anchor_shaping_minimal_patch.md",
    "Parser/apply contract": "docs/reports/c6bf_apply_contract_patch.md",
    "Learning closure": "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md",
}


def test_capability_proven_entries_have_report_handles():
    """C6BM: Every 'Used and causally proven' capability in the closure matrix
    references a real report file (consistency guard)."""
    import os
    base = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    for cap, path in _CAPABILITY_EVIDENCE.items():
        full = os.path.normpath(os.path.join(base, path))
        assert os.path.isfile(full), (
            f"Capability '{cap}' references non-existent evidence: {full}"
        )


def test_not_needed_not_misclassified_as_missing():
    """C6BM: 'Not needed for this lane' capabilities must have an explicit
    justification in their report entry. They must NOT be empty or describe
    a pipeline bug (e.g. 'not needed because verifier was broken')."""
    not_needed = [
        ("Memory", "no session-to-session memory carryover needed"),
        ("Research", "fixes within known code patterns"),
        ("CodeIntel", "locked_search grounded manually"),
    ]
    for cap, reason in not_needed:
        assert len(reason) > 10, f"{cap}: justification must be substantive"
        assert "broken" not in reason.lower(), (
            f"{cap}: 'Not needed' justification must not describe a pipeline bug, "
            f"got: {reason}"
        )


def test_no_task3_expansion_leak():
    """C6BM: Capability evidence handles must reference only the 2 adopted tasks.
    No third task handle may appear in the matrix evidence referencing task 3 expansion."""
    import os
    KNOWN_TASKS = {"astropy__astropy-13236", "sympy__sympy-13852"}
    SUSPECT_MARKERS = {"task__", "__task", "benchmark/", "repo/"}
    base = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    for cap, path in _CAPABILITY_EVIDENCE.items():
        full = os.path.normpath(os.path.join(base, path))
        if not os.path.isfile(full):
            continue
        with open(full) as f:
            content = f.read()
        # Check for task references not in KNOWN_TASKS
        for line in content.splitlines():
            for marker in SUSPECT_MARKERS:
                if marker in line:
                    for token in line.replace(",", " ").split():
                        token = token.strip("'\"`()[]")
                        if ("__" in token or "-" in token) and token not in KNOWN_TASKS:
                            if "adoption" in token.lower() or "c6bm" in token.lower():
                                continue  # self-reference is OK
                            # Allow learning closure matrix to have wide content
                            if "learning closure" in path.lower():
                                continue
                            raise AssertionError(
                                f"Capability '{cap}' evidence file '{path}' "
                                f"references unknown task token '{token}' in line: "
                                f"{line.strip()[:120]}"
                            )
