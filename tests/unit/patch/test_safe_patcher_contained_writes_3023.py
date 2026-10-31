"""SafePatcher writes its repro script and temporary patch file without following links (#3023).

The repro script goes into the project root, where model-run code may already have left a link,
and the temporary patch file goes into the lock dir, which callers may put inside the project
root (``scripts/safepatcher.py`` uses ``<root>/.runs/patches``, the container uses the root
itself). Both writes now go through ``write_text_in_root`` (the lock dir is the root for the
patch file); a refused write skips that violation and leaves the planted entry alone.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import nexus.services.patcher as patcher_module
from nexus.services.patcher import SafePatcher

ORIGINAL = "x = 1\n"
PATCH = "+++ b/calc.py\n+INJECTED = True"
NOW = 1234.5


@pytest.fixture
def layout(tmp_path: Path, monkeypatch) -> tuple[Path, Path, str]:
    root = tmp_path / "root"
    root.mkdir()
    (root / "calc.py").write_text(ORIGINAL, encoding="utf-8")
    outside = tmp_path / "ext" / "host.txt"
    outside.parent.mkdir()
    outside.write_text(ORIGINAL, encoding="utf-8")
    # Fix the clock so the uid in the repro and patch file names is known in advance.
    monkeypatch.setattr(patcher_module, "time", SimpleNamespace(time=lambda: NOW))
    uid = hashlib.md5(f"{NOW}_calc.py".encode()).hexdigest()[:8]
    return root, outside, uid


def _run(patcher: SafePatcher) -> tuple[bool, MagicMock]:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        applied = patcher.apply([{"file": "calc.py", "patch": PATCH}])
    return applied, mock_run


def test_repro_script_is_not_written_through_a_link(layout):
    root, outside, uid = layout
    planted = root / f"reproduce_v{uid}.py"
    os.symlink(outside, planted)
    applied, mock_run = _run(SafePatcher(root / "lock-missing", root))
    assert outside.read_text(encoding="utf-8") == ORIGINAL
    assert planted.is_symlink()
    # The violation is skipped: git apply never runs for it.
    assert applied is False
    assert mock_run.called is False


def test_patch_file_in_a_lock_dir_inside_the_root_is_not_written_through_a_link(layout):
    root, outside, uid = layout
    lock = root / ".runs" / "patches"
    lock.mkdir(parents=True)
    planted = lock / f"auto_{uid}.patch"
    os.symlink(outside, planted)
    applied, mock_run = _run(SafePatcher(lock, root))
    assert outside.read_text(encoding="utf-8") == ORIGINAL
    # The planted entry is not ours: it is neither written through nor removed.
    assert planted.is_symlink()
    assert applied is False
    assert mock_run.called is False


@pytest.mark.parametrize("lock_inside_root", [True, False])
def test_repro_script_and_patch_file_are_still_written(tmp_path, layout, lock_inside_root):
    root, outside, uid = layout
    lock = (root / ".runs" / "patches") if lock_inside_root else (tmp_path / "lock")
    lock.mkdir(parents=True)
    seen: dict[str, str] = {}

    def git_apply(argv, **kwargs):
        seen["patch"] = Path(argv[-1]).read_text(encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=git_apply) as mock_run:
        assert SafePatcher(lock, root).apply([{"file": "calc.py", "patch": PATCH}]) is True
    assert mock_run.call_args[0][0][-1] == str(lock / f"auto_{uid}.patch")
    assert seen["patch"] == PATCH
    # The temporary patch file is removed afterwards, as before.
    assert not (lock / f"auto_{uid}.patch").exists()
    repro = root / f"reproduce_v{uid}.py"
    assert repro.is_file() and not repro.is_symlink()
    assert f"# TDD Reproduce Issue: {uid}" in repro.read_text(encoding="utf-8")
    assert outside.read_text(encoding="utf-8") == ORIGINAL
