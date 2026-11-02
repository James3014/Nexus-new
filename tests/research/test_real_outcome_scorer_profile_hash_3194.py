"""#3194: adding ``/usr/share/locale`` to the shared system read roots keeps the scorer's
"os" profile hash, because the scorer already reads all of ``/usr/share`` (toolchain root).

Earlier "os" receipts and cached results stay comparable. A covered subpath is left out of the
hash only while another read root of the hash covers it; otherwise it changes the hash."""

import os
import sys
from pathlib import Path

from nexus.engine import confined_test_runner
from nexus.engine import sandboxed_lane as lane
from nexus.research import real_outcome_scorer as ros

LOCALE = "/usr/share/locale"
PRE_3194_SUBPATHS = tuple(path for path in lane.SANDBOX_SYSTEM_READ_SUBPATHS if path != LOCALE)


def _hash(scratch: Path) -> str | None:
    runner = ros.PytestRunner(scratch, log=lambda m: None, store=scratch.parent / "_store")
    runner.sandbox = ros.SANDBOX_OS  # the hash needs no barrier, so this runs everywhere
    return runner.sandbox_profile_sha256


def test_locale_root_leaves_the_scorer_profile_hash_unchanged(tmp_path, monkeypatch):
    assert LOCALE in lane.SANDBOX_SYSTEM_READ_SUBPATHS
    assert "/usr/share" in confined_test_runner.TOOLCHAIN_READ_ROOTS
    current = _hash(tmp_path / "now" / "scratch")
    monkeypatch.setattr(lane, "SANDBOX_SYSTEM_READ_SUBPATHS", PRE_3194_SUBPATHS)
    before = _hash(tmp_path / "before" / "scratch")
    assert current == before and len(current or "") == 64


def test_an_uncovered_locale_root_still_changes_the_hash(tmp_path, monkeypatch):
    toolchain = tuple(p for p in confined_test_runner.TOOLCHAIN_READ_ROOTS if p != "/usr/share")
    monkeypatch.setattr(confined_test_runner, "TOOLCHAIN_READ_ROOTS", toolchain)
    with_locale = _hash(tmp_path / "a" / "scratch")
    monkeypatch.setattr(lane, "SANDBOX_SYSTEM_READ_SUBPATHS", PRE_3194_SUBPATHS)
    without_locale = _hash(tmp_path / "b" / "scratch")
    assert with_locale != without_locale


def test_other_shared_root_changes_still_change_the_hash(tmp_path, monkeypatch):
    current = _hash(tmp_path / "a" / "scratch")
    monkeypatch.setattr(
        lane, "SANDBOX_SYSTEM_READ_SUBPATHS", (*lane.SANDBOX_SYSTEM_READ_SUBPATHS, "/usr/share/x")
    )
    # Covered by /usr/share too, but not on the covered list: it is hashed.
    assert _hash(tmp_path / "b" / "scratch") != current


def test_scorer_runs_keep_the_locale_read_root(tmp_path, monkeypatch):
    work = tmp_path / "work"
    tree = work / "trees" / "task" / "cand"
    tree.mkdir(parents=True)
    runner = ros.PytestRunner(work / "scratch", log=lambda m: None, store=work / "_store")
    runner.sandbox = ros.SANDBOX_OS
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    argv = runner._confine(ros.TestEnv("e", sys.executable, "fixture"), tree, work / "r")
    profile = argv[2]
    assert ('(subpath "/usr/share")' in profile) == os.path.exists("/usr/share")
    assert ('(subpath "/usr/share/locale")' in profile) == os.path.isdir(LOCALE)
