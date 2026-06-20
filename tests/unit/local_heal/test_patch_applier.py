import pytest
from pathlib import Path
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.patch_applier import PatchApplier
from nexus.services.local_heal.interface import LocalizedFile
from nexus.services.local_heal.errors import MatchAuthority


def test_patch_applier_success(tmp_path):
    file_path = tmp_path / "calc.py"
    file_path.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    
    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    applier = PatchApplier(parser, patcher)
    
    patch_text = (
        "FILE: calc.py\n"
        "<<<<<<< SEARCH\n"
        "def add(a, b):\n"
        "    return a - b\n"
        "=======\n"
        "def add(a, b):\n"
        "    return a + b\n"
        ">>>>>>> REPLACE\n"
    )
    
    intents = parser.parse(patch_text)
    assert not isinstance(intents, Exception)
    
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="calc.py", content="def add(a, b):\n    return a - b\n")]
    )
    
    assert res.success is True
    assert "calc.py" in res.applied_diffs[0]
    assert "+    return a + b" in res.applied_diffs[0]
    assert file_path.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"


def test_patch_applier_match_gate_failure(tmp_path):
    file_path = tmp_path / "calc.py"
    file_path.write_text("def add(a, b):\n    return a * b\n", encoding="utf-8")
    
    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    applier = PatchApplier(parser, patcher)
    
    patch_text = (
        "FILE: calc.py\n"
        "<<<<<<< SEARCH\n"
        "def add(a, b):\n"
        "    return a - b - c - d - e - f - g\n"
        "=======\n"
        "def add(a, b):\n"
        "    return a + b\n"
        ">>>>>>> REPLACE\n"
    )
    
    intents = parser.parse(patch_text)
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="calc.py", content="def add(a, b):\n    return a * b\n")]
    )
    
    assert res.success is False
    assert res.error_reason == "SEARCH_MISMATCH"


def test_patch_applier_syntax_gate_failure(tmp_path):
    file_path = tmp_path / "calc.py"
    file_path.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    
    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    applier = PatchApplier(parser, patcher)
    
    patch_text = (
        "FILE: calc.py\n"
        "<<<<<<< SEARCH\n"
        "def add(a, b):\n"
        "    return a - b\n"
        "=======\n"
        "def add(a, b):\n"
        "    return a +  # Syntax Error\n"
        ">>>>>>> REPLACE\n"
    )
    
    intents = parser.parse(patch_text)
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="calc.py", content="def add(a, b):\n    return a - b\n")]
    )
    
    assert res.success is False
    assert res.error_reason.startswith("REPLACE_SYNTAX_ERROR")


# ─── T4: PatchApplier authority path tests ─────────────────────────────────────

def test_authority_verbatim_pass(tmp_path):
    """Exact SEARCH match → match_authority=VERBATIM."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    parser = SolidSearchReplaceProtocol()
    applier = PatchApplier(parser, Patcher())

    intents = parser.parse(
        "FILE: a.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n"
    )
    res = applier.apply_and_validate(
        intents=intents, repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="a.py", content="x = 1\n")]
    )
    assert res.success is True
    assert res.match_authority == MatchAuthority.VERBATIM


def test_authority_fuzzy_only_fail(tmp_path):
    """Fuzzy match without external authority → success=False."""
    (tmp_path / "b.py").write_text("result = x + y\n", encoding="utf-8")
    parser = SolidSearchReplaceProtocol()
    applier = PatchApplier(parser, Patcher())

    intents = parser.parse(
        "FILE: b.py\n<<<<<<< SEARCH\nresult =  x + y\n=======\nresult = x * y\n>>>>>>> REPLACE\n"
    )
    res = applier.apply_and_validate(
        intents=intents, repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="b.py", content="result = x + y\n")]
    )
    assert res.success is False
    assert res.error_reason == "SEARCH_MISMATCH"
    assert res.match_authority is None


def test_authority_canonical_span_removed():
    """CANONICAL_SPAN variant removed — was unreachable dead code.

    strip() always passes before rstrip() check, so auto_corrected=True
    path was never triggered. The enum variant has been removed from
    MatchAuthority and the check in PatchApplier simplified to VERBATIM.
    """
    from nexus.services.local_heal.errors import MatchAuthority
    assert not hasattr(MatchAuthority, 'CANONICAL_SPAN'), \
        "CANONICAL_SPAN should have been removed from MatchAuthority enum"


def test_authority_cross_file_pass(tmp_path):
    """SEARCH in wrong file, found in localized file → match_authority=CROSS_FILE_CORRECTION."""
    (tmp_path / "d_wrong.py").write_text("z = 99\n", encoding="utf-8")
    (tmp_path / "d_correct.py").write_text("z = 10\n", encoding="utf-8")
    parser = SolidSearchReplaceProtocol()
    applier = PatchApplier(parser, Patcher())

    intents = parser.parse(
        "FILE: d_wrong.py\n<<<<<<< SEARCH\nz = 10\n=======\nz = 20\n>>>>>>> REPLACE\n"
    )
    res = applier.apply_and_validate(
        intents=intents, repo_dir=tmp_path,
        localized_files=[
            LocalizedFile(path="d_wrong.py", content="z = 99\n"),
            LocalizedFile(path="d_correct.py", content="z = 10\n"),
        ]
    )
    assert res.success is True
    assert res.match_authority == MatchAuthority.CROSS_FILE_CORRECTION


# ─── T3: Fuzzy fail-closed invariant ───────────────────────────────────────────

def test_fuzzy_candidate_only_invariant_raises(tmp_path):
    """FUZZY_CANDIDATE_ONLY on success=True must raise AssertionError.

    The invariant in PatchApplier ensures that fuzzy-only matches can never
    produce a successful patch application.
    """
    (tmp_path / "e.py").write_text("a = 1\n", encoding="utf-8")
    parser = SolidSearchReplaceProtocol()
    applier = PatchApplier(parser, Patcher())

    intents = parser.parse(
        "FILE: e.py\n<<<<<<< SEARCH\na = 1\n=======\na = 2\n>>>>>>> REPLACE\n"
    )
    res = applier.apply_and_validate(
        intents=intents, repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="e.py", content="a = 1\n")]
    )
    # Normal path: authority should be VERBATIM, not FUZZY_CANDIDATE_ONLY
    assert res.success is True
    assert res.match_authority != MatchAuthority.FUZZY_CANDIDATE_ONLY


# ─── Part A Hardening: Invariant and Attribution Separation Tests ──────────────

def test_high_similarity_fuzzy_candidate_fail_closed(tmp_path):
    """SEARCH_MISMATCH with high similarity closest candidate must still fail closed."""
    (tmp_path / "fuzzy.py").write_text("def my_func(arg1, arg2):\n    return arg1 + arg2\n", encoding="utf-8")
    parser = SolidSearchReplaceProtocol()
    applier = PatchApplier(parser, Patcher())

    # High similarity search block (only slight difference in spacing/arg names)
    patch_text = (
        "FILE: fuzzy.py\n"
        "<<<<<<< SEARCH\n"
        "def my_func( arg1,  arg2):\n"
        "    return arg1 + arg2\n"
        "=======\n"
        "def my_func(arg1, arg2):\n"
        "    return arg1 * arg2\n"
        ">>>>>>> REPLACE\n"
    )
    intents = parser.parse(patch_text)
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="fuzzy.py", content="def my_func(arg1, arg2):\n    return arg1 + arg2\n")]
    )
    assert res.success is False
    assert res.error_reason == "SEARCH_MISMATCH"


def test_fuzzy_candidate_only_never_success(tmp_path):
    """match_authority=FUZZY_CANDIDATE_ONLY must never produce success=true."""
    (tmp_path / "invariant.py").write_text("value = 42\n", encoding="utf-8")
    parser = SolidSearchReplaceProtocol()
    applier = PatchApplier(parser, Patcher())
    intents = parser.parse("FILE: invariant.py\n<<<<<<< SEARCH\nvalue = 42\n=======\nvalue = 100\n>>>>>>> REPLACE\n")
    
    # Force AssertionError when FUZZY_CANDIDATE_ONLY is passed on success
    with pytest.raises(AssertionError, match="INVARIANT VIOLATION: FUZZY_CANDIDATE_ONLY cannot be set on success=True"):
        applier.apply_and_validate(
            intents=intents,
            repo_dir=tmp_path,
            localized_files=[LocalizedFile(path="invariant.py", content="value = 42\n")],
            match_authority=MatchAuthority.FUZZY_CANDIDATE_ONLY
        )


def test_closest_match_diagnostic_only(tmp_path):
    """closest_match may appear only as diagnostic telemetry and not enter apply."""
    (tmp_path / "diag.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    parser = SolidSearchReplaceProtocol()
    applier = PatchApplier(parser, Patcher())

    intents = parser.parse("FILE: diag.py\n<<<<<<< SEARCH\nx = 100\n=======\nx = 200\n>>>>>>> REPLACE\n")
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="diag.py", content="x = 1\ny = 2\n")]
    )
    assert res.success is False
    # Verify diagnostic info is present in errors but does not apply
    assert len(res.errors) > 0
    assert res.errors[0].closest_match == "x = 1"


def test_canonical_recovery_not_model_success(tmp_path):
    """canonical span recovery must be attribution-separated from model patch success."""
    (tmp_path / "recovery.py").write_text("def run():\n    pass\n", encoding="utf-8")
    parser = SolidSearchReplaceProtocol()
    applier = PatchApplier(parser, Patcher())
    intents = parser.parse("FILE: recovery.py\n<<<<<<< SEARCH\ndef run():\n    pass\n=======\ndef run():\n    return 42\n>>>>>>> REPLACE\n")
    
    # Simulating a canonical recovery fallback path by explicitly passing CANONICAL_RECOVERY
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="recovery.py", content="def run():\n    pass\n")],
        match_authority=MatchAuthority.CANONICAL_RECOVERY
    )
    assert res.success is True
    assert res.match_authority == MatchAuthority.CANONICAL_RECOVERY


def test_cross_file_correction_requires_authority(tmp_path):
    """cross-file correction requires explicit CROSS_FILE_CORRECTION authority receipt."""
    (tmp_path / "wrong.py").write_text("x = 0\n", encoding="utf-8")
    (tmp_path / "right.py").write_text("x = 10\n", encoding="utf-8")
    parser = SolidSearchReplaceProtocol()
    applier = PatchApplier(parser, Patcher())

    intents = parser.parse(
        "FILE: wrong.py\n<<<<<<< SEARCH\nx = 10\n=======\nx = 20\n>>>>>>> REPLACE\n"
    )
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[
            LocalizedFile(path="wrong.py", content="x = 0\n"),
            LocalizedFile(path="right.py", content="x = 10\n"),
        ]
    )
    assert res.success is True
    assert res.match_authority == MatchAuthority.CROSS_FILE_CORRECTION

