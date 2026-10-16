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
    assert "set -uo pipefail" in script and "set -e" not in script.replace("set -euo", "")
