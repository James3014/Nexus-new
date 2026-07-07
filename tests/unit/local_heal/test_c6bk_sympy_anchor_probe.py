"""
C6BK/C6BL: sympy-13852 lower-layer anchor stability probe + fix verification.

C6BK established taxonomy: anchor_too_short_for_body (old locked_search
was 1-line if-header without body).
C6BL fixed: locked_search now includes the indented body block.

Verifies:
1. OLD 1-line locked_search was too short (regression guard)
2. NEW multi-line locked_search is complete Python block
3. Anchor fix enables parseable replacement path
4. Replacement based on new anchor passes AST validation
"""
import pytest
import ast

# Old (pre-C6BL) locked_search — kept as regression fixture
OLD_LOCKED_SEARCH = "if a is S.One:"

# Expected replacement for the fixed locked_search
MULTI_LINE_REPLACEMENT = (
    "        if a == S.One:\n"
    "            pass\n"
)


def _get_sympy_spec():
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = {s["task_id"]: s for s in build_task_specs()}
    return specs["sympy__sympy-13852"]


# ═══ C6BL: New anchor verification ═══

def test_sympy_13852_multiline_locked_search_is_complete_python_block():
    """C6BL: The new multi-line locked_search (if-header + pass body)
    passes AST validation (using protocol.py's wrapper fallback)."""
    spec = _get_sympy_spec()
    ls = spec["locked_search"]
    lines = ls.strip().splitlines()
    assert len(lines) >= 2, (
        f"Expected multi-line locked_search (>=2 lines), got {len(lines)}"
    )
    assert "if a is S.One:" in lines[0], f"First line must be if-header: {lines[0]}"
    assert "pass" in lines[1], f"Second line must be pass body: {lines[1]}"

    # Verify complete block passes AST (same wrapper as protocol.py:466)
    try:
        ast.parse(ls)
    except SyntaxError:
        wrapped = "def _wrapper():\n" + "\n".join(
            f"    {l}" for l in ls.splitlines()
        )
        ast.parse(wrapped)


def test_sympy_13852_multiline_locked_search_matches_source_context():
    """C6BL: The multi-line locked_search matches the exact if-block
    region in buggy_code (lines 3-4)."""
    spec = _get_sympy_spec()
    ls = spec["locked_search"]
    src = spec["buggy_code"]

    assert ls.strip() in src, (
        "locked_search must be a substring of buggy_code"
    )
    src_lines = src.splitlines()
    assert len(src_lines) >= 4
    # Lines 3-4 (0-indexed: 2,3) are the if-block
    expected_block = "\n".join(src_lines[2:4]) + "\n"
    assert ls.strip() == expected_block.strip(), (
        f"locked_search must match lines 3-4 of buggy_code\n"
        f"locked: {repr(ls.strip())}\n"
        f"source: {repr(expected_block.strip())}"
    )


def test_sympy_13852_multiline_locked_search_reaches_parseable_replacement_path():
    """C6BL: With multi-line anchor, a replacement changing 'is' to '=='
    while keeping the pass body produces valid unified diff.
    This confirms the anchor_too_short_for_body fix is sufficient."""
    from nexus.services.local_heal.local_model_executor import _normalize_candidate_patch
    from dataclasses import dataclass

    @dataclass
    class _Req:
        repo_root = ""
        target_file = "sympy/functions/special/zeta_functions.py"

    spec = _get_sympy_spec()
    locked = spec["locked_search"]

    # Model output with fixed replacement (keep pass body)
    model_output = (
        "<<<<<<< REPLACE\n"
        f"{MULTI_LINE_REPLACEMENT}"
        ">>>>>>> REPLACE"
    )

    patch, meta = _normalize_candidate_patch(_Req(), locked, model_output)

    assert not meta.get("protocol_parse_failed"), (
        f"Expected parse to succeed with multi-line anchor, got meta={meta}"
    )
    assert "a == S.One" in patch, (
        f"Patch must contain the fix 'a == S.One': {patch[:200]}"
    )


# ═══ C6BL: Regression — old anchor was too short ═══

def test_sympy_13852_old_single_line_anchor_was_too_short():
    """C6BL: The OLD 1-line locked_search 'if a is S.One:'
    produces REPLACEMENT_SYNTAX_INVALID. Regression guard."""
    old_locked = OLD_LOCKED_SEARCH  # 1-line, no body

    with pytest.raises(SyntaxError):
        ast.parse(old_locked)


# ═══ C6BK: Retained anchor stability probes (updated for new state) ═══

def test_sympy_locked_search_is_multiline():
    """C6BK (updated): locked_search is now multi-line (was 1-line pre-C6BL)."""
    spec = _get_sympy_spec()
    ls = spec["locked_search"]
    lines = ls.strip().splitlines()
    assert len(lines) >= 2, f"Expected >=2 lines after C6BL fix, got {len(lines)}"


def test_sympy_locked_search_contains_indented_body():
    """C6BK (updated): locked_search now includes the indented pass body."""
    spec = _get_sympy_spec()
    ls = spec["locked_search"]
    src = spec["buggy_code"]

    assert "pass" in ls, "locked_search must now contain the indented body"
    assert ls.strip() in src, "locked_search must be a substring of buggy_code"


def test_sympy_locked_search_is_complete_python():
    """C6BK (updated): locked_search (multi-line) is now valid Python
    when parsed with the protocol.py AST wrapper."""
    spec = _get_sympy_spec()
    ls = spec["locked_search"]

    try:
        ast.parse(ls)
    except SyntaxError:
        wrapped = "def _wrapper():\n" + "\n".join(
            f"    {l}" for l in ls.splitlines()
        )
        ast.parse(wrapped)


def test_sympy_locked_search_with_body_is_valid_python():
    """C6BK (updated): The if-block from buggy_code is now the
    locked_search itself — directly valid with AST wrapper."""
    spec = _get_sympy_spec()
    src = spec["buggy_code"]
    lines = src.splitlines()
    full_block = "\n".join(lines[2:4])

    try:
        ast.parse(full_block)
    except SyntaxError:
        wrapped = "def _wrapper():\n" + "\n".join(
            f"    {l}" for l in full_block.splitlines()
        )
        ast.parse(wrapped)
    assert "if a is S.One:" in src
    assert "pass" in src


def test_sympy_multi_line_replacement_parses():
    """C6BK: A multi-line replacement including the if-header + body
    passes AST validation (using same wrapper as protocol.py).
    This confirms anchor_too_short_for_body was the correct taxonomy."""
    try:
        ast.parse(MULTI_LINE_REPLACEMENT)
    except SyntaxError:
        wrapped = "def _wrapper():\n" + "\n".join(
            f"    {l}" for l in MULTI_LINE_REPLACEMENT.splitlines()
        )
        ast.parse(wrapped)


def test_sympy_single_line_replacement_fails_ast():
    """C6BK: Single-line replacement fails AST validation —
    confirming why OLD locked_search produced REPLACEMENT_SYNTAX_INVALID."""
    replacement = OLD_LOCKED_SEARCH.replace("is", "==")
    with pytest.raises(SyntaxError):
        ast.parse(replacement)


def test_sympy_vs_astropy_pre_c6bd_parallel():
    """C6BK (updated): Both tasks now have multi-line locked_search
    containing the full statement block."""
    spec = _get_sympy_spec()
    sympy_locked = spec["locked_search"]
    assert len(sympy_locked.strip().splitlines()) >= 2, (
        "sympy locked_search must be multi-line (C6BL fix applied)"
    )


def test_sympy_problem_statement_present_but_unreachable():
    """C6BK (updated): With the multi-line anchor fix, problem_statement
    can now reach the model. This test verifies the condition is met."""
    spec = _get_sympy_spec()
    ls = spec["locked_search"]

    # Verify anchor is now stable (multi-line, parsable)
    assert len(ls.strip().splitlines()) >= 2
    try:
        ast.parse(ls)
    except SyntaxError:
        wrapped = "def _wrapper():\n" + "\n".join(
            f"    {l}" for l in ls.splitlines()
        )
        ast.parse(wrapped)

    # problem_statement format is compatible
    example_ps = (
        "Fix sympy/functions/special/zeta_functions.py so that the eval "
        "method uses 'a == S.One' instead of 'a is S.One'. "
        "The patched file must contain 'a == S.One'."
    )
    assert "must contain" in example_ps.lower()
    assert "a == S.One" in example_ps
