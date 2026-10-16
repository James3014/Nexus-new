"""The bindings preflight runs on GitHub from the default branch, never PR code (#2365)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "pr-bindings-preflight.yml"
CONTEXT = "Bindings preflight (default branch)"


def _load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job() -> dict:
    return _load()["jobs"]["bindings-preflight"]


def test_runs_default_branch_copy_on_pr_target_including_body_edits() -> None:
    data = _load()
    triggers = data.get("on", data.get(True))
    assert set(triggers) == {"pull_request_target"}
    target = triggers["pull_request_target"]
    assert target["branches"] == ["main"]
    # a body edit must re-evaluate the bindings without a push
    assert set(target["types"]) == {"opened", "synchronize", "reopened", "edited"}


def test_least_privilege_and_no_pr_checkout() -> None:
    data = _load()
    assert data["permissions"] == {}
    job = _job()
    assert job["permissions"] == {
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
        "statuses": "write",
    }
    checkout = next(s for s in job["steps"] if "actions/checkout" in s.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert checkout["with"]["persist-credentials"] is False
    text = WORKFLOW.read_text(encoding="utf-8")
    # the PR head is only fetched as objects and pinned to the event's head sha
    assert 'fetch --no-tags origin "refs/pull/${PR}/head"' in text
    assert 'test "$(git rev-parse FETCH_HEAD)" = "$HEAD_SHA"' in text
    # the derived base64 credential is masked and never on argv
    assert 'echo "::add-mask::${auth}"' in text
    assert "git -c " not in text
    for forbidden in ("git checkout", "git switch", "uv sync", "pip install", "PYTHONPATH"):
        assert forbidden not in text


def test_runs_the_bindings_check_isolated_and_publishes_the_status() -> None:
    run = next(s for s in _job()["steps"] if s.get("name", "").startswith("Run the bindings"))
    script = run["run"]
    assert "python3 -I scripts/ops/pr_preflight.py" in script
    assert "--only bindings --no-fetch" in script
    assert '--head "$HEAD_SHA"' in script
    assert run["env"]["CONTEXT"] == CONTEXT
    assert "statuses/${HEAD_SHA}" in script
    # the job's own result follows the check, so it cannot go green on a FAIL
    assert script.rstrip().endswith('exit "$rc"')
    assert "set +e -uo pipefail" in script
    # printed preflight output cannot run workflow commands
    assert (
        script.index("::stop-commands::")
        < script.index('cat "$out"')
        < script.index('echo "::${stop}::"')
    )


def test_status_goes_pending_before_any_step_can_fail() -> None:
    steps = _job()["steps"]
    names = [s.get("name", "") for s in steps]
    pending = names.index("Mark the status pending before anything can fail")
    assert pending < names.index("Fetch the PR head as git objects only")
    assert "state=pending" in steps[pending]["run"]
    assert steps[pending]["env"]["CONTEXT"] == CONTEXT


def _run_publish_step(tmp_path: Path, preflight_output: str, preflight_rc: int) -> tuple[int, str]:
    """Execute the real publish step with fake python3/gh on PATH."""
    import os
    import stat
    import subprocess

    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True)
    (bindir / "python3").write_text(
        f"#!/bin/sh\ncat <<'OUT'\n{preflight_output}\nOUT\nexit {preflight_rc}\n", encoding="utf-8"
    )
    posted = tmp_path / "posted.txt"
    (bindir / "gh").write_text(f'#!/bin/sh\necho "$@" >> {posted}\n', encoding="utf-8")
    for tool in ("python3", "gh"):
        (bindir / tool).chmod(stat.S_IRWXU)
    run = next(s for s in _job()["steps"] if s.get("name", "").startswith("Run the bindings"))
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "RUNNER_TEMP": str(tmp_path),
        "REPO": "o/r",
        "PR": "1",
        "HEAD_SHA": "a" * 40,
        "RUN_URL": "u",
        "CONTEXT": CONTEXT,
        "HOME": os.environ.get("HOME", str(tmp_path)),
    }
    proc = subprocess.run(["bash", "-e", "-c", run["run"]], env=env, capture_output=True, text=True)
    return proc.returncode, posted.read_text(encoding="utf-8")


def test_publish_step_pass_fail_and_skip(tmp_path: Path) -> None:
    rc, posted = _run_publish_step(tmp_path / "pass", "PASS  bindings: ok\nRESULT: PASS", 0)
    assert rc == 0 and "state=success" in posted
    rc, posted = _run_publish_step(tmp_path / "fail", "FAIL  bindings [X]: bad\nRESULT: FAIL", 1)
    assert rc == 1 and "state=failure" in posted
    # exit 0 without a PASS line (SKIP) must not publish success
    rc, posted = _run_publish_step(
        tmp_path / "skip", "SKIP  bindings: gate missing\nRESULT: PASS", 0
    )
    assert rc == 1 and "state=failure" in posted and "state=success" not in posted
