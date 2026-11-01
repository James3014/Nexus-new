"""#3084: the review-record job marks its status pending first and never leaves an old success.

Both copies of the job (Nexus-new's own workflow and the reusable sibling workflow)
must set "Review record present (advisory)" to pending on the PR head before the
check runs, let only the completed check publish success, and mark the status
error when the check does not finish (failure, cancellation or step timeout).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ops import review_record_check as rrc

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
FILES = ("review-record-present.yml", "sibling-merge-checks.yml")
HEAD = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"
SEP = "\x1f"


def _job(name: str) -> dict[str, Any]:
    doc = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return doc["jobs"]["review-record"]


def _index(steps: list[dict[str, Any]], predicate) -> int:
    hits = [i for i, step in enumerate(steps) if predicate(step)]
    assert len(hits) == 1, hits
    return hits[0]


def _posts_status(step: dict[str, Any]) -> bool:
    return "/statuses/" in step.get("run", "")


def _runs_check(step: dict[str, Any]) -> bool:
    return "scripts/ops/review_record_check.py" in step.get("run", "")


@pytest.mark.parametrize("name", FILES)
def test_pending_is_posted_first_with_the_same_context(name: str) -> None:
    job = _job(name)
    steps = job["steps"]
    assert job["env"]["CONTEXT"] == rrc.STATUS_CONTEXT
    first_post = next(i for i, step in enumerate(steps) if _posts_status(step))
    check = _index(steps, _runs_check)
    assert first_post == 0 < check
    pending = steps[first_post]
    assert "if" not in pending
    assert pending["id"] == "pending"
    run = pending["run"]
    assert "-f state=pending" in run
    assert '-f context="$CONTEXT"' in run
    # The same head the check reads: the live PR head from pulls/N, validated.
    assert 'gh api "repos/${REPO}/pulls/${PR}" --jq .head.sha' in run
    assert "^[0-9a-f]{40}$" in run
    assert run.index("^[0-9a-f]{40}$") < run.index("/statuses/")
    assert 'echo "head_sha=${head}" >> "$GITHUB_OUTPUT"' in run


@pytest.mark.parametrize("name", FILES)
def test_unfinished_check_marks_the_status_non_success(name: str) -> None:
    job = _job(name)
    steps = job["steps"]
    check = _index(steps, _runs_check)
    assert steps[check]["id"] == "check"
    # A slow check fails its own step before the job timeout, so cleanup still runs.
    assert steps[check]["timeout-minutes"] < job["timeout-minutes"]
    cleanup = steps[-1]
    assert check < len(steps) - 1
    assert cleanup["if"] == "(failure() || cancelled()) && steps.check.outcome != 'success'"
    assert cleanup["env"]["HEAD_SHA"] == "${{ steps.pending.outputs.head_sha }}"
    run = cleanup["run"]
    assert "-f state=error" in run
    assert '-f context="$CONTEXT"' in run
    assert "success" not in run
    # Pending, check and cleanup step budgets leave the checkout room in the job timeout.
    budget = sum(s.get("timeout-minutes", 0) for s in steps)
    assert budget < job["timeout-minutes"]


@pytest.mark.parametrize("name", FILES)
def test_only_the_completed_check_can_publish_success(name: str) -> None:
    job = _job(name)
    for step in job["steps"]:
        run = step.get("run", "")
        assert "state=success" not in run
        assert "${{" not in run  # values reach the shell through env only
    posts = [i for i, step in enumerate(job["steps"]) if _posts_status(step)]
    check = _index(job["steps"], _runs_check)
    assert posts == [0, len(job["steps"]) - 1] and posts[0] < check < posts[1]
    assert "--no-fail" in job["steps"][check]["run"]
    # No new permission: the job already had statuses: write and pull-requests: read.
    assert job["permissions"] == {
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
        "statuses": "write",
    }


def _dry_run(tmp_path: Path, run: str, gh_head: str, extra: dict[str, str]):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    calls = tmp_path / "calls.txt"
    calls.write_text("", encoding="utf-8")
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    gh = bindir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        f'for a in "$@"; do printf \'%s{SEP}\' "$a" >> "{calls}"; done\n'
        f"printf '\\n' >> \"{calls}\"\n"
        'case "$*" in *--jq*) printf \'%s\\n\' "$FAKE_HEAD";; esac\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", str(tmp_path)),
        "GITHUB_OUTPUT": str(output),
        "RUNNER_TEMP": str(tmp_path),
        "CONTEXT": rrc.STATUS_CONTEXT,
        "GH_TOKEN": "fake-token",
        "REPO": "o/r",
        "PR": "7",
        "RUN_URL": "https://github.com/o/r/actions/runs/1",
        "FAKE_HEAD": gh_head,
        **extra,
    }
    proc = subprocess.run(["bash", "-e", "-c", run], env=env, capture_output=True, text=True)
    recorded = [
        line.split(SEP)[:-1] for line in calls.read_text(encoding="utf-8").splitlines() if line
    ]
    return proc.returncode, recorded, output.read_text(encoding="utf-8")


def _status_call(sha: str, state: str, description: str) -> list[str]:
    return [
        "api",
        "-X",
        "POST",
        f"repos/o/r/statuses/{sha}",
        "-f",
        f"state={state}",
        "-f",
        f"context={rrc.STATUS_CONTEXT}",
        "-f",
        "target_url=https://github.com/o/r/actions/runs/1",
        "-f",
        f"description={description}",
    ]


READ_HEAD = ["api", "repos/o/r/pulls/7", "--jq", ".head.sha"]


@pytest.mark.parametrize("name", FILES)
def test_pending_step_dry_run_posts_pending_on_the_live_head(name: str, tmp_path: Path) -> None:
    run = _job(name)["steps"][0]["run"]
    rc, calls, output = _dry_run(tmp_path, run, HEAD, {})
    assert rc == 0
    assert calls == [READ_HEAD, _status_call(HEAD, "pending", "evaluating the review record")]
    assert output == f"head_sha={HEAD}\n"


@pytest.mark.parametrize("name", FILES)
def test_pending_step_refuses_an_invalid_head(name: str, tmp_path: Path) -> None:
    run = _job(name)["steps"][0]["run"]
    rc, calls, output = _dry_run(tmp_path, run, "not-a-sha; echo x", {})
    assert rc != 0
    assert calls == [READ_HEAD]
    assert output == ""


@pytest.mark.parametrize("name", FILES)
def test_cleanup_dry_run_marks_the_pending_head_error(name: str, tmp_path: Path) -> None:
    job = _job(name)
    run = job["steps"][-1]["run"]
    rc, calls, _ = _dry_run(tmp_path, run, OTHER, {"HEAD_SHA": HEAD})
    assert rc == 0
    assert calls == [_status_call(HEAD, "error", "review record check did not finish; see the run")]


@pytest.mark.parametrize("name", FILES)
def test_cleanup_dry_run_reads_the_head_when_pending_never_ran(name: str, tmp_path: Path) -> None:
    run = _job(name)["steps"][-1]["run"]
    rc, calls, _ = _dry_run(tmp_path, run, HEAD, {"HEAD_SHA": ""})
    assert rc == 0
    assert calls == [
        READ_HEAD,
        _status_call(HEAD, "error", "review record check did not finish; see the run"),
    ]
    rc, calls, _ = _dry_run(tmp_path, run, "", {"HEAD_SHA": "x"})
    assert rc != 0
    assert calls == [READ_HEAD]
