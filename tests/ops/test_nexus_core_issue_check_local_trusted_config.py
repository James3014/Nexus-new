"""nexus-core-issue-check-local with the pinned Core: config comes from the base commit.

These run the real Core CLI at the workflow's pin (offline Issue reader, no
network) against a throwaway repository. Locally they skip when the pinned Core
cannot be obtained; in CI they fail instead of skipping.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-core-issue-check-local"
WORKFLOW = ".github/workflows/nexus-core-issue-completion.yml"
CORE_GITHUB_URL = "https://github.com/James3014/nexus-core.git"
CONFIG_REASONS = {"CONFIG_SOURCE_MISMATCH", "CONFIG_UNTRUSTED"}

CORE_WRAPPER = """import json, sys, urllib.request

sys.path.insert(0, sys.argv.pop(1))


def _offline(*_args, **_kwargs):
    raise OSError("network is disabled in this test")


urllib.request.urlopen = _offline
from product.clients import issue_golden_path

issue_golden_path._default_issue_reader = lambda _repo, number: {
    "number": number,
    "title": "local check fixture",
    "body": "fixture",
    "state": "open",
    "author_association": "OWNER",
    "user": {"login": "fixture"},
}
from product.clients.cli import main

sys.exit(main())
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, timeout=120
    ).stdout.strip()


def _pinned_core_revision() -> str:
    text = (ROOT / WORKFLOW).read_text(encoding="utf-8")
    pins = set(re.findall(r'nexus-certify-ref:\s*"([0-9a-f]{40})"', text))
    assert len(pins) == 1, pins
    return pins.pop()


def _core_unobtainable(message: str) -> None:
    """Skip locally, but never let CI pass by skipping (#2201)."""
    if os.environ.get("CI", "").strip():
        pytest.fail(f"{message} (CI forbids skipping the pinned-Core tests)")
    pytest.skip(message)


def _materialize_core(dest: Path, revision: str) -> str | None:
    """Clean detached Core checkout at ``revision``; returns a reason on failure."""

    def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=300, check=False
        )

    errors = []
    source = os.environ.get("NEXUS_CORE_REPO_ROOT", "").strip()
    if source and (Path(source) / ".git").exists():
        cloned = run("clone", "-q", "--no-checkout", source, str(dest), cwd=dest.parent)
        if (
            cloned.returncode == 0
            and run("checkout", "-q", "--detach", revision, cwd=dest).returncode == 0
        ):
            return None
        errors.append(f"local clone of {source} lacks {revision}")
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    run("init", "-q", cwd=dest)
    fetched = run("fetch", "-q", "--depth", "1", CORE_GITHUB_URL, revision, cwd=dest)
    if (
        fetched.returncode == 0
        and run("checkout", "-q", "--detach", "FETCH_HEAD", cwd=dest).returncode == 0
    ):
        return None
    errors.append(f"fetch from {CORE_GITHUB_URL} failed: {fetched.stderr.strip()[:200]}")
    return "; ".join(errors)


@pytest.fixture(scope="module")
def pinned_core(tmp_path_factory) -> Path:
    revision = _pinned_core_revision()
    dest = tmp_path_factory.mktemp("core") / "nexus-core"
    reason = _materialize_core(dest, revision)
    if reason is not None:
        _core_unobtainable(f"pinned nexus-core {revision} not obtainable: {reason}")
    assert _git(dest, "rev-parse", "HEAD") == revision
    return dest


def _config(base_ref: str, marker: Path) -> str:
    return f'''version = 2
base_ref = "{base_ref}"
allowed_patterns = ["**"]
deletion_policy = "FORBID"
universe_generation = 2
materials = []

[[verifiers]]
id = "v"
command = ["/bin/sh", "-c", "echo ran > {marker}"]
timeout_seconds = 60
logical_subject_id = "fixture/v"
evidence_kind = "test-result"
requirement_mode = "REQUIRED"
applicability = "APPLICABLE"
'''


def _repo(tmp: Path, universe: str | None = "trusted-config") -> tuple[Path, Path]:
    """A repository whose base commit carries a config with a harmless verifier.

    The base workflow declares ``universe`` as its evidence universe (the real gate
    workflow declares trusted-config); None leaves it undeclared (Core's issue-marker).
    """
    bare = tmp / "origin.git"
    repo = tmp / "repo"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / ".github/workflows").mkdir(parents=True)
    workflow = "env:\n  NEXUS_CORE_TOOL_PIN: " + "a" * 40 + "\n"
    if universe is not None:
        workflow += f"jobs:\n  run:\n    with:\n      evidence-universe: {universe}\n"
    (repo / WORKFLOW).write_text(workflow)
    (repo / ".nexus-core").mkdir()
    base_marker = tmp / "base-verifier-ran"
    (repo / ".nexus-core/config.toml").write_text(_config("origin/main", base_marker))
    (repo / ".gitignore").write_text(".nexus-core/receipts/\n.nexus-core/issues/\n")
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "fetch", "-q", "origin", "main")
    _git(repo, "checkout", "-q", "-b", "candidate")
    return repo, base_marker


def _run_tool(
    tmp: Path, repo: Path, core: Path
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    wrapper = tmp / "core_wrapper.py"
    wrapper.write_text(CORE_WRAPPER)
    certify = tmp / "nexus-certify"
    certify.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I -B "{wrapper}" "{core}" "$@"\n')
    certify.chmod(0o755)
    # The origin URL only names the repository for the offline Issue reader.
    _git(repo, "remote", "set-url", "origin", "https://github.com/James3014/fixture.git")
    home = tmp / "home"
    home.mkdir()
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "GITHUB_TOKEN": "fixture-token",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--issue",
        "7",
        "--repo-root",
        str(repo),
        "--certify-bin",
        str(certify),
        "--no-fetch",
        "--cache-root",
        str(tmp / "cache"),
        "--output-dir",
        str(tmp / "out"),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=tmp,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        pytest.fail(f"tool did not finish: {err[-2000:]}")
    done = subprocess.CompletedProcess(cmd, proc.returncode, out, err)
    return done, json.loads(out)


def _log(summary: dict[str, Any]) -> str:
    return Path(summary["log_path"]).read_text(encoding="utf-8")


def test_issue_check_uses_trusted_base_config_only(pinned_core, tmp_path):
    """A candidate head that edits the config gets a config-trust failure; its verifier never runs."""
    # issue-marker universe: issue-init accepts the binding, so issue-check's trust flags decide.
    repo, base_marker = _repo(tmp_path, universe=None)
    candidate_marker = tmp_path / "candidate-verifier-ran"
    (repo / ".nexus-core/config.toml").write_text(_config("HEAD~1", candidate_marker))
    _git(repo, "commit", "-q", "-am", "candidate config")
    (repo / "a.txt").write_text("b\n")
    _git(repo, "commit", "-q", "-am", "candidate change")

    proc, summary = _run_tool(tmp_path, repo, pinned_core)

    assert proc.returncode == 1, proc.stderr + proc.stdout
    assert summary["status"] != "VERIFIED"
    log = _log(summary)
    assert re.search(r"^\$ issue-check \(exit [1-9]", log, re.MULTILINE), log
    assert CONFIG_REASONS & set(summary["reason_codes"]), (summary, log)
    assert not candidate_marker.exists()
    assert not base_marker.exists()


def test_issue_check_accepts_base_config_at_base_commit(pinned_core, tmp_path):
    """With an unchanged config, Core takes it from the pinned base commit and runs its verifier."""
    repo, base_marker = _repo(tmp_path)
    (repo / "a.txt").write_text("b\n")
    _git(repo, "commit", "-q", "-am", "candidate change")

    proc, summary = _run_tool(tmp_path, repo, pinned_core)

    log = _log(summary)
    assert summary["base_sha"] == _git(repo, "rev-parse", "origin/main")
    assert not CONFIG_REASONS & set(summary["reason_codes"]), (summary, log)
    assert "CONFIG_SOURCE_MISMATCH" not in log and "CONFIG_UNTRUSTED" not in log, log
    assert base_marker.read_text().strip() == "ran", (proc.stderr, log)
    assert proc.returncode == 0, (summary, log)
    assert summary["status"] == "VERIFIED", (summary, log)


def test_unchanged_base_config_is_verified_like_ci(pinned_core, tmp_path):
    """The base workflow declares evidence-universe trusted-config, so the local run, like CI,
    needs no Issue marker: a clean candidate is VERIFIED from the receipt Core reports."""
    repo, base_marker = _repo(tmp_path)
    (repo / "a.txt").write_text("b\n")
    _git(repo, "commit", "-q", "-am", "candidate change")

    proc, summary = _run_tool(tmp_path, repo, pinned_core)

    log = _log(summary)
    assert "ISSUE_EVIDENCE_UNIVERSE_UNBOUND" not in log, log
    assert proc.returncode == 0, (summary, log)
    assert summary["status"] == "VERIFIED", (summary, log)
    assert Path(summary["receipt_path"]).parent == tmp_path / "out"


def test_trusted_universe_refuses_candidate_config(pinned_core, tmp_path):
    """With the base's trusted-config universe, a candidate config edit fails closed; no verifier runs."""
    repo, base_marker = _repo(tmp_path)
    candidate_marker = tmp_path / "candidate-verifier-ran"
    (repo / ".nexus-core/config.toml").write_text(_config("HEAD~1", candidate_marker))
    _git(repo, "commit", "-q", "-am", "candidate config")
    (repo / "a.txt").write_text("b\n")
    _git(repo, "commit", "-q", "-am", "candidate change")

    proc, summary = _run_tool(tmp_path, repo, pinned_core)

    log = _log(summary)
    assert proc.returncode == 1, (summary, log)
    assert summary["status"] != "VERIFIED"
    assert summary["receipt_path"] is None, (summary, log)
    assert "CONFIG_UNTRUSTED" in log or CONFIG_REASONS & set(summary["reason_codes"]), log
    assert not candidate_marker.exists()
    assert not base_marker.exists()


def test_candidate_config_from_another_trusted_ref_is_refused(pinned_core, tmp_path):
    """The candidate config names another committed ref whose config it matches, so Core would
    treat it as a trusted base-ref config; the base-commit pin still refuses it before any
    verifier runs."""
    repo, base_marker = _repo(tmp_path)
    other_marker = tmp_path / "other-ref-verifier-ran"
    other_config = _config("other-trusted", other_marker)
    _git(repo, "checkout", "-q", "-b", "other-trusted", "main")
    (repo / ".nexus-core/config.toml").write_text(other_config)
    _git(repo, "commit", "-q", "-am", "config on another ref")
    other_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "candidate")
    (repo / ".nexus-core/config.toml").write_text(other_config)
    _git(repo, "commit", "-q", "-am", "candidate config")
    (repo / "a.txt").write_text("b\n")
    _git(repo, "commit", "-q", "-am", "candidate change")

    proc, summary = _run_tool(tmp_path, repo, pinned_core)

    log = _log(summary)
    assert summary["base_sha"] != other_sha
    assert proc.returncode == 1, (summary, log)
    assert summary["status"] != "VERIFIED", (summary, log)
    assert "CONFIG_SOURCE_MISMATCH" in log or "CONFIG_SOURCE_MISMATCH" in summary["reason_codes"], (
        summary,
        log,
    )
    assert not other_marker.exists()
    assert not base_marker.exists()
