"""The manifest read runs every git call pinned to the probed git dir (#3148 item 4).

Without the pin git would rediscover the repository from the work tree at each call, and a
concurrent writer could swap what it finds between the probe and the read. A discovery-based
call and a pinned call only differ when the probe answers something else than discovery does,
so the test makes the probe answer a second git dir inside the Target.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator import canonical_core_transport as transport


def _git(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.run(
        ["git", "-c", "commit.gpgSign=false", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(path: Path, name: str) -> tuple[Path, str]:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@nexus.internal")
    (path / f"{name}.txt").write_text(f"{name}\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", name)
    return path, _git(path, "rev-parse", "HEAD")


def test_manifest_reads_the_probed_git_dir_not_the_one_discovery_finds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    target, target_commit = _repo(tmp_path / "target", "target")
    other, base = _repo(tmp_path / "other", "base")
    (other / "added.txt").write_text("added\n", encoding="utf-8")
    _git(other, "add", ".")
    _git(other, "commit", "-qm", "added")
    head = _git(other, "rev-parse", "HEAD")
    assert target_commit not in (base, head)
    alt = target / "alt.git"
    _git(tmp_path, "clone", "-q", "--bare", str(other), str(alt))

    monkeypatch.setattr(transport.hardened_git, "repository_git_dir", lambda _r: alt)

    manifest = transport.extract_git_manifest(target, base, head)

    assert [e["path"] for e in manifest["entries"]] == ["added.txt"]
