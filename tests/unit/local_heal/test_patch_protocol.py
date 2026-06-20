import pytest
from pathlib import Path
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.corrector import SelfCorrector
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.patch_applier import PatchApplier
from nexus.services.local_heal.interface import LocalizedFile


def test_patch_empty_retry_prompt():
    corrector = SelfCorrector()
    error = PatchError(kind=PatchErrorKind.PATCH_EMPTY, message="apply produced no diff")
    prompt = corrector.build_retry_prompt("[TASK] Fix bug", error)
    assert "ZERO file changes" in prompt
    assert "SEARCH and REPLACE are identical" not in prompt.split("PATCH_EMPTY")[0] if "PATCH_EMPTY" in prompt else True
    assert "SEARCH/REPLACE" in prompt


def test_patch_format_invalid_retry_prompt():
    corrector = SelfCorrector()
    error = PatchError(kind=PatchErrorKind.PATCH_FORMAT_INVALID, message="missing >>>>>>> SEARCH marker")
    prompt = corrector.build_retry_prompt("[TASK] Fix bug", error)
    assert "not in valid SEARCH/REPLACE format" in prompt
    assert ">>>>>>>" in prompt


def test_source_stale_retry_prompt():
    corrector = SelfCorrector()
    error = PatchError(kind=PatchErrorKind.SOURCE_STALE, message="file modified since context capture")
    prompt = corrector.build_retry_prompt("[TASK] Fix bug", error)
    assert "outdated" in prompt
    assert "current file state" in prompt


def test_failure_class_enum_has_new_values():
    assert hasattr(PatchErrorKind, "PATCH_EMPTY")
    assert hasattr(PatchErrorKind, "PATCH_FORMAT_INVALID")
    assert hasattr(PatchErrorKind, "SOURCE_STALE")


def test_existing_retry_prompts_still_work():
    corrector = SelfCorrector()

    syntax_error = PatchError(kind=PatchErrorKind.SYNTAX_ERROR, message="SyntaxError at line 5")
    prompt = corrector.build_retry_prompt("[TASK] Fix bug", syntax_error)
    assert "syntax compilation error" in prompt

    name_sanity = PatchError(kind=PatchErrorKind.NAME_SANITY_ERROR, message="duplicate class Foo")
    prompt = corrector.build_retry_prompt("[TASK] Fix bug", name_sanity)
    assert "code sanity checks" in prompt

    no_blocks = PatchError(kind=PatchErrorKind.NO_BLOCKS_FOUND, message="no SEARCH/REPLACE blocks")
    prompt = corrector.build_retry_prompt("[TASK] Fix bug", no_blocks)
    assert "ZERO SEARCH/REPLACE blocks" in prompt


def test_retry_prompt_strips_old_hud():
    corrector = SelfCorrector()
    old_prompt = (
        "[TASK] Fix bug\n\n"
        "⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]\n"
        "Old warning content here"
    )
    error = PatchError(kind=PatchErrorKind.SYNTAX_ERROR, message="SyntaxError")
    new_prompt = corrector.build_retry_prompt(old_prompt, error)
    assert new_prompt.count("⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]") == 1
    assert "Old warning content" not in new_prompt


# ─── T1: Fuzzy authority fail-closed ───────────────────────────────────────────
# Fuzzy-only matches (no external canonical authority) MUST fail with SEARCH_MISMATCH.
# This prevents silent same-file fuzzy apply.

def test_fuzzy_only_must_fail_closed(tmp_path):
    """Fuzzy candidate with high similarity but no verbatim match must NOT auto-apply.

    Regression guard: patch_applier.py had a fuzzy_sim >= 0.95 path that
    allowed same-file canonical injection without external authority. This test
    ensures that path is dead-closed — SEARCH_MISMATCH with requires_authority=True.
    """
    source = (
        "def calculate(x, y):\n"
        "    result = x + y\n"
        "    return result\n"
    )
    (tmp_path / "math.py").write_text(source, encoding="utf-8")

    # SEARCH is close but not verbatim (extra space, slight drift)
    # DiffLibFuzzyMatcher will find it with high similarity
    patch_text = (
        "FILE: math.py\n"
        "<<<<<<< SEARCH\n"
        "def calculate(x, y):\n"
        "    result =  x + y\n"
        "    return result\n"
        "=======\n"
        "def calculate(x, y):\n"
        "    result = x + y\n"
        "    return result + 1\n"
        ">>>>>>> REPLACE\n"
    )

    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    applier = PatchApplier(parser, patcher)

    intents = parser.parse(patch_text)
    assert not isinstance(intents, Exception)

    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="math.py", content=source)]
    )

    # Fuzzy-only must fail-closed
    assert res.success is False
    assert res.error_reason == "SEARCH_MISMATCH"

    # Verify requires_authority telemetry is set
    if res.errors:
        err = res.errors[0]
        assert err.telemetry is not None
        assert err.telemetry.get("requires_authority") is True


def test_fuzzy_high_sim_no_external_authority_fails(tmp_path):
    """Even similarity >= 0.95 without external canonical authority must fail."""
    source = (
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 42\n"
    )
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")

    # SEARCH has single-char drift — high fuzzy sim but not verbatim
    patch_text = (
        "FILE: mod.py\n"
        "<<<<<<< SEARCH\n"
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 41\n"
        "=======\n"
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 99\n"
        ">>>>>>> REPLACE\n"
    )

    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    applier = PatchApplier(parser, patcher)

    intents = parser.parse(patch_text)
    assert not isinstance(intents, Exception)

    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="mod.py", content=source)]
    )

    assert res.success is False
    assert res.error_reason == "SEARCH_MISMATCH"


# ─── T8: Historical SEARCH_MISMATCH replay ─────────────────────────────────────
# Prove that a high-fuzzy candidate that would have previously auto-applied
# (via the now-removed fuzzy_sim>=0.95 path) correctly returns SEARCH_MISMATCH.

def test_historical_search_mismatch_no_false_success(tmp_path):
    """Simulate a historical SEARCH_MISMATCH candidate with high fuzzy similarity.

    Before the fix (T2), patch_applier.py had a path where fuzzy_sim >= 0.95
    allowed same-file canonical injection. This replay proves that path is dead:
    the same scenario now returns SEARCH_MISMATCH instead of false success.
    """
    source = (
        "class separability_matrix:\n"
        "    def __init__(self, matrix):\n"
        "        self.matrix = matrix\n"
        "\n"
        "    def is_connected(self):\n"
        "        return all(any(row) for row in self.matrix)\n"
    )
    (tmp_path / "separability.py").write_text(source, encoding="utf-8")

    # SEARCH has character-level drift (not whitespace) — truly non-verbatim
    # DiffLibFuzzyMatcher will find it with high similarity
    patch_text = (
        "FILE: separability.py\n"
        "<<<<<<< SEARCH\n"
        "class separability_matrix:\n"
        "    def __init__(self, matrix):\n"
        "        self.matrix = matrix\n"
        "\n"
        "    def is_connected(self):\n"
        "        return all(any(row) for row in self.matrix)\n"
        "=======\n"
        "class separability_matrix:\n"
        "    def __init__(self, matrix):\n"
        "        self.matrix = matrix\n"
        "\n"
        "    def is_connected(self):\n"
        "        return any(all(row) for row in self.matrix)\n"
        ">>>>>>> REPLACE\n"
    )

    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    applier = PatchApplier(parser, patcher)

    intents = parser.parse(patch_text)
    assert not isinstance(intents, Exception)

    # Patch the search to add a non-verbatim difference (change a char)
    intents[0].search = intents[0].search.replace(
        "return all(any(row) for row in self.matrix)",
        "return all(any(rows) for row in self.matrix)"
    )

    # Verify the search is NOT in source (truly non-verbatim)
    source_text = (tmp_path / "separability.py").read_text()
    assert intents[0].search not in source_text, "SEARCH must be non-verbatim"

    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="separability.py", content=source)]
    )

    # FAIL-CLOSED: must NOT false success
    assert res.success is False, "Historical SEARCH_MISMATCH must not false-success"
    assert res.error_reason == "SEARCH_MISMATCH"
    assert res.match_authority is None
