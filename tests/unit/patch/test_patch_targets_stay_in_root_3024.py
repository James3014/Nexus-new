"""Patch targets named by model output stay inside the project root (#3024).

- Patch Apply v2: TargetFileDiscovery takes the target from diff headers or file-name lines in
  the model's raw output, and PatchApplyEngine reads and writes ``project_root / target``. An
  absolute path, ``..``, or a link in the root must not take the write outside the root.
- direct_mode.extract_target_files (also run on model output) drops ``..`` paths.
- SafePatcher's direct-write fallback writes the file a reviewer verdict names: same rule.

Every case checks that the file outside the root keeps its exact content.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexus.engine.direct_mode import extract_target_files
from nexus.engine.patch.apply_engine import PatchApplyEngine
from nexus.engine.patch.target_discovery import TargetFileDiscovery
from nexus.services.patcher import SafePatcher

ORIGINAL = "x = 1\n"

BLOCK = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n"


def _raw(target: str) -> str:
    return f"--- a/{target}\n+++ b/{target}\n{BLOCK}"


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "root"
    root.mkdir()
    (root / "calc.py").write_text(ORIGINAL, encoding="utf-8")
    ext = tmp_path / "ext"
    ext.mkdir()
    (ext / "calc.py").write_text(ORIGINAL, encoding="utf-8")
    return root, ext / "calc.py"


def _resolve_and_apply(root: Path, raw: str, context_files: list[str] | None = None):
    """What engine/phases/repair.py does with the model's raw output."""

    resolution = TargetFileDiscovery().resolve(
        raw, context_files=context_files or [], project_root=str(root)
    )
    if not (resolution.resolved and resolution.target_file):
        return resolution, None
    return resolution, PatchApplyEngine(root).apply_patch("t3024", str(resolution.target_file), raw)


# --- Patch Apply v2: target resolution -------------------------------------------------------


def test_discovery_refuses_dotdot_header_target(layout):
    root, outside = layout
    resolution, applied = _resolve_and_apply(root, _raw("../ext/calc.py"))
    assert resolution.resolved is False
    assert "TARGET_OUTSIDE_PROJECT_ROOT" in (resolution.reason or "")
    assert applied is None
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_discovery_refuses_absolute_header_target(layout):
    root, outside = layout
    resolution, applied = _resolve_and_apply(root, _raw(str(outside)))
    assert resolution.resolved is False
    assert "TARGET_OUTSIDE_PROJECT_ROOT" in (resolution.reason or "")
    assert applied is None
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_discovery_refuses_absolute_file_name_line_target(layout):
    root, outside = layout
    resolution, applied = _resolve_and_apply(root, f"{outside}\n{BLOCK}")
    assert resolution.resolved is False
    assert applied is None
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_discovery_refuses_dotdot_context_target_without_project_root(layout):
    resolution = TargetFileDiscovery().resolve(BLOCK, context_files=["../ext/calc.py"])
    assert resolution.resolved is False
    assert "TARGET_OUTSIDE_PROJECT_ROOT" in (resolution.reason or "")


def test_discovery_refuses_absolute_context_target_without_project_root(layout):
    _, outside = layout
    resolution = TargetFileDiscovery().resolve(BLOCK, context_files=[str(outside)])
    assert resolution.resolved is False
    assert "TARGET_OUTSIDE_PROJECT_ROOT" in (resolution.reason or "")


def test_discovery_refuses_link_leaving_root(layout):
    root, outside = layout
    os.symlink(outside, root / "linked.py")
    resolution, applied = _resolve_and_apply(root, _raw("linked.py"))
    assert resolution.resolved is False
    assert "TARGET_OUTSIDE_PROJECT_ROOT" in (resolution.reason or "")
    assert applied is None
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_discovery_refuses_linked_directory_leaving_root(layout):
    root, outside = layout
    os.symlink(outside.parent, root / "vendor")
    resolution, applied = _resolve_and_apply(root, _raw("vendor/calc.py"))
    assert resolution.resolved is False
    assert applied is None
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_discovery_does_not_take_stripped_prefix_link_leaving_root(layout):
    root, outside = layout
    os.symlink(outside, root / "linked.py")
    # "+++ b/b/linked.py" captures "b/linked.py", which does not exist; the a/ b/ strip fallback
    # then tries "linked.py".
    resolution, applied = _resolve_and_apply(root, _raw("b/linked.py"))
    assert not (resolution.resolved and resolution.target_file == "linked.py")
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_discovery_and_apply_inside_root_still_work(layout):
    root, outside = layout
    resolution, applied = _resolve_and_apply(root, _raw("calc.py"))
    assert resolution.resolved is True
    assert resolution.target_file == "calc.py"
    assert applied is not None and applied["success"] is True
    assert (root / "calc.py").read_text(encoding="utf-8") == "x = 2\n"
    assert outside.read_text(encoding="utf-8") == ORIGINAL


# --- Patch Apply v2: the engine itself (pipeline_repair passes its own target) ----------------


@pytest.mark.parametrize("kind", ["dotdot", "absolute", "file_link", "dir_link"])
def test_apply_engine_never_writes_outside_root(layout, kind):
    root, outside = layout
    if kind == "dotdot":
        target = "../ext/calc.py"
    elif kind == "absolute":
        target = str(outside)
    elif kind == "file_link":
        os.symlink(outside, root / "linked.py")
        target = "linked.py"
    else:
        os.symlink(outside.parent, root / "vendor")
        target = "vendor/calc.py"
    result = PatchApplyEngine(root).apply_patch("t3024", target, BLOCK)
    assert result.get("success") is not True
    assert result.get("status") == "FAIL"
    assert "OUTSIDE_PROJECT_ROOT" in result.get("reason", "")
    assert outside.read_text(encoding="utf-8") == ORIGINAL
    assert (root / "calc.py").read_text(encoding="utf-8") == ORIGINAL


def test_apply_engine_does_not_write_through_hard_link(layout):
    root, outside = layout
    os.link(outside, root / "hard.py")
    result = PatchApplyEngine(root).apply_patch("t3024", "hard.py", BLOCK)
    assert result.get("success") is not True
    # Refused at the read, before the patch is parsed or a receipt is written.
    assert result.get("status") == "FAIL"
    assert "TARGET_FILE_REFUSED" in result.get("reason", "")
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_apply_engine_inside_root_still_writes(layout):
    root, outside = layout
    (root / "pkg").mkdir()
    (root / "pkg" / "mod.py").write_text(ORIGINAL, encoding="utf-8")
    result = PatchApplyEngine(root).apply_patch("t3024", "pkg/mod.py", BLOCK)
    assert result["success"] is True
    assert (root / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 2\n"
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_apply_engine_missing_file_inside_root_reports_not_found(layout):
    root, _ = layout
    result = PatchApplyEngine(root).apply_patch("t3024", "nope.py", BLOCK)
    assert result == {"status": "FAIL", "reason": "FILE_NOT_FOUND: nope.py"}


# --- direct_mode.extract_target_files on model output ----------------------------------------


def test_extract_target_files_drops_dotdot_paths():
    text = "fix ../ext/calc.py:3 and pkg/../../ext/calc.py, keep pkg/mod.py\n" + _raw(
        "../ext/calc.py"
    )
    assert extract_target_files(text) == ["pkg/mod.py"]


def test_extract_target_files_keeps_normal_paths():
    assert extract_target_files("edit nexus/engine/direct_mode.py:12 and ./tests/a_test.py") == [
        "nexus/engine/direct_mode.py",
        "./tests/a_test.py",
    ]


# --- SafePatcher direct-write fallback ---------------------------------------------------------


def _patcher(tmp_path: Path, root: Path) -> SafePatcher:
    lock = tmp_path / "lock"
    lock.mkdir()
    return SafePatcher(lock, root)


def _apply_with_git_failing(
    patcher: SafePatcher, file_name: str, *, expect_git: bool = True
) -> bool:
    violations = [{"file": file_name, "patch": f"+++ b/{file_name}\n+INJECTED = True"}]
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        applied = patcher.apply(violations)
    # A target outside the root is skipped before git apply runs.
    assert mock_run.called is expect_git
    return applied


@pytest.mark.parametrize("kind", ["dotdot", "absolute", "file_link", "dir_link"])
def test_patcher_fallback_never_writes_outside_root(tmp_path, layout, kind):
    root, outside = layout
    if kind == "dotdot":
        target = "../ext/calc.py"
    elif kind == "absolute":
        target = str(outside)
    elif kind == "file_link":
        os.symlink(outside, root / "linked.py")
        target = "linked.py"
    else:
        os.symlink(outside.parent, root / "vendor")
        target = "vendor/calc.py"
    assert _apply_with_git_failing(_patcher(tmp_path, root), target, expect_git=False) is False
    assert outside.read_text(encoding="utf-8") == ORIGINAL
    assert not list(root.glob("reproduce_v*.py"))


def test_patcher_fallback_does_not_write_through_hard_link(tmp_path, layout):
    root, outside = layout
    os.link(outside, root / "hard.py")
    assert _apply_with_git_failing(_patcher(tmp_path, root), "hard.py") is False
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_patcher_fallback_inside_root_still_writes(tmp_path, layout):
    root, outside = layout
    assert _apply_with_git_failing(_patcher(tmp_path, root), "calc.py") is True
    assert "INJECTED = True" in (root / "calc.py").read_text(encoding="utf-8")
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_apply_engine_does_not_follow_link_swapped_in_before_write(layout, monkeypatch):
    root, outside = layout
    engine = PatchApplyEngine(root)
    real_verify = engine.verifier.verify_change

    def verify_then_swap(original, current):
        # Model-run code could replace the file with a link after the read.
        (root / "calc.py").unlink()
        os.symlink(outside, root / "calc.py")
        return real_verify(original, current)

    monkeypatch.setattr(engine.verifier, "verify_change", verify_then_swap)
    result = engine.apply_patch("t3024", "calc.py", BLOCK)
    assert result["success"] is False
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_patcher_fallback_does_not_follow_link_swapped_in_after_check(tmp_path, layout):
    root, outside = layout

    def git_fails_after_swap(*args, **kwargs):
        (root / "calc.py").unlink()
        os.symlink(outside, root / "calc.py")
        return MagicMock(returncode=1)

    violations = [{"file": "calc.py", "patch": "+++ b/calc.py\n+INJECTED = True"}]
    with patch("subprocess.run", side_effect=git_fails_after_swap):
        assert _patcher(tmp_path, root).apply(violations) is False
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_patcher_fallback_write_does_not_follow_link_swapped_in_after_read(
    tmp_path, layout, monkeypatch
):
    import nexus.services.patcher as patcher_module

    root, outside = layout
    real_read = patcher_module.read_text_in_root

    def read_then_swap(*args, **kwargs):
        text = real_read(*args, **kwargs)
        (root / "calc.py").unlink()
        os.symlink(outside, root / "calc.py")
        return text

    monkeypatch.setattr(patcher_module, "read_text_in_root", read_then_swap)
    assert _apply_with_git_failing(_patcher(tmp_path, root), "calc.py") is False
    assert outside.read_text(encoding="utf-8") == ORIGINAL


# --- Files the helpers would change beyond the patch: not UTF-8, read-only ----------------------

LATIN1 = b"# caf\xe9 latin-1\nx = 1\n"


def test_apply_engine_refuses_non_utf8_target_and_keeps_its_bytes(layout):
    root, _ = layout
    (root / "legacy.py").write_bytes(LATIN1)
    result = PatchApplyEngine(root).apply_patch("t3024", "legacy.py", BLOCK)
    assert result.get("success") is not True
    assert result.get("status") == "FAIL"
    assert (root / "legacy.py").read_bytes() == LATIN1


def test_patcher_fallback_refuses_non_utf8_target_and_keeps_its_bytes(tmp_path, layout):
    root, _ = layout
    (root / "legacy.py").write_bytes(LATIN1)
    assert _apply_with_git_failing(_patcher(tmp_path, root), "legacy.py") is False
    assert (root / "legacy.py").read_bytes() == LATIN1


def test_apply_engine_refuses_read_only_target(layout):
    root, _ = layout
    (root / "calc.py").chmod(0o444)
    result = PatchApplyEngine(root).apply_patch("t3024", "calc.py", BLOCK)
    assert result.get("success") is not True
    assert result.get("status") == "FAIL"
    assert (root / "calc.py").read_text(encoding="utf-8") == ORIGINAL


def test_patcher_fallback_refuses_read_only_target(tmp_path, layout):
    root, _ = layout
    (root / "calc.py").chmod(0o444)
    assert _apply_with_git_failing(_patcher(tmp_path, root), "calc.py") is False
    assert (root / "calc.py").read_text(encoding="utf-8") == ORIGINAL


def test_discovery_git_change_fallback_skips_link_leaving_root(layout):
    root, outside = layout
    os.symlink(outside, root / "linked.py")
    git_status = MagicMock(returncode=0, stdout=" M linked.py\n")
    with patch("subprocess.run", return_value=git_status):
        resolution = TargetFileDiscovery().resolve(BLOCK, context_files=[], project_root=str(root))
    assert resolution.resolved is False
    assert outside.read_text(encoding="utf-8") == ORIGINAL


def test_discovery_git_change_fallback_still_takes_file_inside_root(layout):
    root, _ = layout
    git_status = MagicMock(returncode=0, stdout=" M calc.py\n")
    with patch("subprocess.run", return_value=git_status):
        resolution = TargetFileDiscovery().resolve(BLOCK, context_files=[], project_root=str(root))
    assert resolution.resolved is True
    assert resolution.target_file == "calc.py"
