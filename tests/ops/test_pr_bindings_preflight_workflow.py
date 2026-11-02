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
    triggers = data["on"] if "on" in data else data[True]
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
    # Pending is the first step: a checkout that fails or times out cannot leave an
    # earlier run's success standing (#3084 pattern).
    checkout = next(i for i, s in enumerate(steps) if "actions/checkout" in s.get("uses", ""))
    assert pending == 0 < checkout
    assert pending < names.index("Fetch the PR head as git objects only")
    assert "state=pending" in steps[pending]["run"]
    assert steps[pending]["env"]["CONTEXT"] == CONTEXT


def _run_publish_step(
    tmp_path: Path, preflight_output: str, preflight_rc: int, gh_rc: int = 0
) -> tuple[int, str]:
    """Execute the real publish step with fake python3/gh on PATH."""
    import os
    import stat
    import subprocess

    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True)
    (bindir / "python3").write_text(
        # answer only the preflight call; the stop-token call fails, so the fallback runs
        '#!/bin/sh\ncase "$*" in *secrets*) echo junk; exit 1;; esac\n'
        f"cat <<'OUT'\n{preflight_output}\nOUT\nexit {preflight_rc}\n",
        encoding="utf-8",
    )
    posted = tmp_path / "posted.txt"
    (bindir / "gh").write_text(
        f'#!/bin/sh\necho "$@" >> {posted}\nexit {gh_rc}\n', encoding="utf-8"
    )
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
        "GITHUB_OUTPUT": str(tmp_path / "github_output"),
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


def test_publish_step_fails_when_status_post_fails(tmp_path: Path) -> None:
    """A PASS whose final status POST fails must not leave the job green."""
    rc, posted = _run_publish_step(tmp_path, "PASS  bindings: ok\nRESULT: PASS", 0, gh_rc=1)
    assert "state=success" in posted and rc == 1


# --- #3084 pattern for the bindings preflight: pending first, error on an unfinished run.

HEAD = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"
SEP = "\x1f"
PENDING_HEAD = "${{ steps.pending.outputs.head_sha }}"
ERROR_IF = "(failure() || cancelled()) && steps.publish.outputs.published != 'true'"
ERROR_DESCRIPTION = "bindings preflight did not finish; see the run"


def _posts_status(step: dict) -> bool:
    return "/statuses/" in step.get("run", "")


def _publish_index(steps: list[dict]) -> int:
    hits = [i for i, s in enumerate(steps) if "scripts/ops/pr_preflight.py" in s.get("run", "")]
    assert len(hits) == 1, hits
    return hits[0]


def test_pending_step_reads_and_validates_the_live_head_before_posting() -> None:
    pending = _job()["steps"][0]
    assert pending["id"] == "pending"
    assert "if" not in pending and "uses" not in pending
    assert pending["timeout-minutes"] == 1
    run = pending["run"]
    assert 'gh api "repos/${REPO}/pulls/${PR}" --jq .head.sha' in run
    assert run.index("^[0-9a-f]{40}$") < run.index('>> "$GITHUB_OUTPUT"') < run.index("/statuses/")
    assert 'echo "head_sha=${head}" >> "$GITHUB_OUTPUT"' in run
    assert "-f state=pending" in run and '-f context="$CONTEXT"' in run


def test_later_steps_check_and_mark_the_pending_head() -> None:
    steps = _job()["steps"]
    for step in steps[1:]:
        if "run" in step:
            assert step["env"]["HEAD_SHA"] == PENDING_HEAD, step.get("name")
    for step in steps:
        # values reach the shell through env only
        assert "${{" not in step.get("run", "")


def test_checkout_has_a_step_timeout_below_the_job_timeout() -> None:
    job = _job()
    steps = job["steps"]
    checkout = next(s for s in steps if "actions/checkout" in s.get("uses", ""))
    assert 0 < checkout["timeout-minutes"] < job["timeout-minutes"]
    # Every step has its own budget and together they fit in the job timeout, so a
    # slow step fails on its own and the error step still runs.
    assert all("timeout-minutes" in s for s in steps)
    assert sum(s["timeout-minutes"] for s in steps) < job["timeout-minutes"]


def test_unfinished_run_marks_the_status_error() -> None:
    steps = _job()["steps"]
    publish = _publish_index(steps)
    error = steps[-1]
    assert publish == len(steps) - 2
    assert steps[publish]["id"] == "publish"
    assert error["if"] == ERROR_IF
    assert error["env"]["HEAD_SHA"] == PENDING_HEAD
    assert error["env"]["CONTEXT"] == CONTEXT
    run = error["run"]
    assert "-f state=error" in run and '-f context="$CONTEXT"' in run
    assert "success" not in run
    # The publish step records that it posted its result only after the POST succeeded.
    script = steps[publish]["run"]
    flag = script.index('echo "published=true" >> "$GITHUB_OUTPUT"')
    assert script.index("/statuses/${HEAD_SHA}") < flag < script.rindex('exit "$rc"')


def test_only_the_publish_step_can_post_success() -> None:
    steps = _job()["steps"]
    publish = _publish_index(steps)
    posts = [i for i, step in enumerate(steps) if _posts_status(step)]
    assert posts == [0, publish, len(steps) - 1]
    for i, step in enumerate(steps):
        if i != publish:
            run = step.get("run", "")
            assert "state=success" not in run and '-f state="$state"' not in run


def _dry_run(tmp_path: Path, run: str, gh_head: str, extra: dict[str, str]):
    import os
    import subprocess

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
        "CONTEXT": CONTEXT,
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
        f"context={CONTEXT}",
        "-f",
        "target_url=https://github.com/o/r/actions/runs/1",
        "-f",
        f"description={description}",
    ]


READ_HEAD = ["api", "repos/o/r/pulls/7", "--jq", ".head.sha"]


def test_pending_step_dry_run_posts_pending_on_the_live_head(tmp_path: Path) -> None:
    run = _job()["steps"][0]["run"]
    rc, calls, output = _dry_run(tmp_path, run, HEAD, {})
    assert rc == 0
    assert calls == [READ_HEAD, _status_call(HEAD, "pending", "bindings preflight running")]
    assert output == f"head_sha={HEAD}\n"


def test_pending_step_dry_run_refuses_an_invalid_head(tmp_path: Path) -> None:
    run = _job()["steps"][0]["run"]
    rc, calls, output = _dry_run(tmp_path, run, "not-a-sha; echo x", {})
    assert rc != 0
    assert calls == [READ_HEAD]
    assert output == ""


def test_error_step_dry_run_marks_the_pending_head_error(tmp_path: Path) -> None:
    run = _job()["steps"][-1]["run"]
    rc, calls, _ = _dry_run(tmp_path, run, OTHER, {"HEAD_SHA": HEAD})
    assert rc == 0
    assert calls == [_status_call(HEAD, "error", ERROR_DESCRIPTION)]


def test_error_step_dry_run_reads_the_head_when_pending_never_ran(tmp_path: Path) -> None:
    run = _job()["steps"][-1]["run"]
    rc, calls, _ = _dry_run(tmp_path, run, HEAD, {"HEAD_SHA": ""})
    assert rc == 0
    assert calls == [READ_HEAD, _status_call(HEAD, "error", ERROR_DESCRIPTION)]
    rc, calls, _ = _dry_run(tmp_path, run, "", {"HEAD_SHA": "x"})
    assert rc != 0
    assert calls == [READ_HEAD]


def test_publish_step_records_published_only_after_its_post(tmp_path: Path) -> None:
    for name, out, rc_in, gh_rc, expect in (
        ("pass", "PASS  bindings: ok", 0, 0, "published=true\n"),
        ("fail", "FAIL  bindings [X]: bad", 1, 0, "published=true\n"),
        ("postfail", "PASS  bindings: ok", 0, 1, ""),
    ):
        _run_publish_step(tmp_path / name, out, rc_in, gh_rc)
        output = tmp_path / name / "github_output"
        assert (output.read_text(encoding="utf-8") if output.exists() else "") == expect, name
