"""Trusted dependency-contract check split out of the trusted controller (#2156)."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

import scripts.ops.trusted_deletion_anchor as anchor
import scripts.ops.trusted_dependency_contract as tdc

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/trusted-dependency-contract.yml"
REPOSITORY = "James3014/Nexus-new"
PR = 4242
PYPROJECT = b"[project]\nname = 'fixture'\nversion = '0'\n"
UV_LOCK = b"version = 1\nrevision = 3\n"
JOB = "trusted-dependency-contract"
STEP = "Acquire exact trusted source and check the dependency contract"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class Fixture:
    """A main history in ``origin.git`` plus a PR head pushed to refs/pull/N/head."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.work = root / "work"
        self.origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.work)], check=True)
        _git(self.work, "config", "user.email", "test@example.invalid")
        _git(self.work, "config", "user.name", "dependency-contract-test")
        _git(self.work, "config", "commit.gpgsign", "false")
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin)], check=True)
        _git(self.work, "remote", "add", "origin", str(self.origin))
        self.write("pyproject.toml", PYPROJECT)
        self.write("uv.lock", UV_LOCK)
        self.write("product/__init__.py", b"")
        self.write("README.md", b"fixture\n")
        self.fork_point = self.commit("main: initial")

    def write(self, path: str, content: bytes) -> None:
        target = self.work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        target.write_bytes(content)

    def commit(self, message: str) -> str:
        _git(self.work, "add", "-A")
        _git(self.work, "commit", "-q", "--allow-empty", "-m", message)
        return _git(self.work, "rev-parse", "HEAD")

    def branch(self, name: str, start: str) -> None:
        _git(self.work, "checkout", "-q", "-B", name, start)

    def publish(self, main_sha: str, head_sha: str) -> None:
        _git(self.work, "push", "-q", "-f", "origin", f"{main_sha}:refs/heads/main")
        _git(self.work, "push", "-q", "-f", "origin", f"{head_sha}:refs/pull/{PR}/head")

    def controller_repo(self, main_sha: str) -> Path:
        """The workflow's bare repo: depth-1 fetch of the trusted commit only."""

        repo = self.root / "ctrl.git"
        shutil.rmtree(repo, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "--bare", str(repo)], check=True)
        _git(repo, "remote", "add", "origin", self.origin.as_uri())
        _git(repo, "fetch", "-q", "--no-tags", "--depth=1", "origin", main_sha)
        return repo


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


def _event(main_sha: str, head_sha: str, **overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_name": "pull_request_target",
        "workflow_ref": f"{REPOSITORY}/{tdc.WORKFLOW_PATH}@refs/heads/main",
        "workflow_sha": main_sha,
        "run_id": 7,
        "repository": {"full_name": REPOSITORY, "default_branch": "main"},
        "pull_request": {
            "number": PR,
            "body": None,
            "base": {"ref": "main", "sha": main_sha, "repo": {"full_name": REPOSITORY}},
            "head": {"sha": head_sha, "repo": {"full_name": REPOSITORY}},
        },
    }
    event.update(overrides)
    return event


def _run(fx: Fixture, main_sha: str, head_sha: str) -> dict[str, Any]:
    fx.publish(main_sha, head_sha)
    repo = fx.controller_repo(main_sha)
    return tdc.evaluate(repo, tdc.identity(_event(main_sha, head_sha)))


def _authorize(monkeypatch: pytest.MonkeyPatch, number: int, transition: tuple) -> None:
    # Stand-in for an Owner-approved anchor already on main: replace one slot of the
    # validator's authorized table (the validator reads these globals at call time).
    monkeypatch.setattr(
        anchor, "TRUSTED_PR2122_DEPENDENCY_SNAPSHOT_TRANSITION", (number, transition)
    )


def _hashes(trusted: tuple[bytes, bytes], head: tuple[bytes, bytes]) -> tuple[str, ...]:
    return (
        anchor._sha(trusted[0]),
        anchor._sha(trusted[1]),
        anchor._sha(head[0]),
        anchor._sha(head[1]),
    )


# ----------------------------------------------------------------- green verdicts


def test_pr_touching_neither_file_passes(fx: Fixture) -> None:
    fx.branch("pr", fx.fork_point)
    fx.write("README.md", b"changed\n")
    head = fx.commit("pr: docs only")
    record = _run(fx, fx.fork_point, head)
    assert record["status"] == "PASS"
    assert record["reason_code"] == tdc.UNCHANGED


def test_untouched_files_pass_even_when_main_moved_them_after_the_fork(fx: Fixture) -> None:
    fx.write("pyproject.toml", PYPROJECT + b"# main moved\n")
    fx.write("uv.lock", UV_LOCK + b"# main moved\n")
    main = fx.commit("main: dependency bump after the PR forked")
    fx.branch("pr", fx.fork_point)
    fx.write("README.md", b"changed\n")
    head = fx.commit("pr: docs only")
    record = _run(fx, main, head)
    assert record["status"] == "PASS"
    assert record["reason_code"] == tdc.UNTOUCHED
    assert record["merge_base_sha"] == fx.fork_point


def test_byte_identical_files_pass_after_edit_and_revert(fx: Fixture) -> None:
    fx.branch("pr", fx.fork_point)
    fx.write("pyproject.toml", PYPROJECT + b"# temporary\n")
    fx.commit("pr: edit")
    fx.write("pyproject.toml", PYPROJECT)
    head = fx.commit("pr: revert")
    record = _run(fx, fx.fork_point, head)
    assert (record["status"], record["reason_code"]) == ("PASS", tdc.UNCHANGED)


def test_byte_identical_to_main_passes_when_pr_adopts_mains_new_bytes(fx: Fixture) -> None:
    fx.write("uv.lock", UV_LOCK + b"# main moved\n")
    main = fx.commit("main: lock refresh")
    fx.branch("pr", fx.fork_point)
    fx.write("uv.lock", UV_LOCK + b"# main moved\n")
    head = fx.commit("pr: same bytes as main, authored independently")
    record = _run(fx, main, head)
    assert (record["status"], record["reason_code"]) == ("PASS", tdc.UNCHANGED)


def test_exact_anchor_on_main_passes(fx: Fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    new_pyproject = PYPROJECT + b"dependencies = ['x==1']\n"
    new_lock = UV_LOCK + b"# x 1\n"
    fx.branch("pr", fx.fork_point)
    fx.write("pyproject.toml", new_pyproject)
    fx.write("uv.lock", new_lock)
    head = fx.commit("pr: dependency change")
    _authorize(monkeypatch, PR, _hashes((PYPROJECT, UV_LOCK), (new_pyproject, new_lock)))
    record = _run(fx, fx.fork_point, head)
    assert (record["status"], record["reason_code"]) == ("PASS", tdc.AUTHORIZED)


def test_check_ignores_pr_body_and_merge_lane_binding(fx: Fixture) -> None:
    fx.branch("pr", fx.fork_point)
    fx.write("README.md", b"changed\n")
    head = fx.commit("pr: docs only")
    fx.publish(fx.fork_point, head)
    repo = fx.controller_repo(fx.fork_point)
    for body in (None, "", "no lane block", "<!-- NEXUS_MERGE_LANE_V1 garbage -->"):
        event = _event(fx.fork_point, head)
        event["pull_request"]["body"] = body
        event["pull_request"]["user"] = {"login": "James3014", "type": "User"}
        assert tdc.evaluate(repo, tdc.identity(event))["status"] == "PASS"
    source = (ROOT / "scripts/ops/trusted_dependency_contract.py").read_text(encoding="utf-8")
    assert "trusted_merge_lane_gate" not in source
    assert '"body"' not in source


# ----------------------------------------------------------------- red verdicts


@pytest.mark.parametrize("path", ["pyproject.toml", "uv.lock"])
def test_unanchored_change_is_drift(fx: Fixture, path: str) -> None:
    fx.branch("pr", fx.fork_point)
    fx.write(path, (PYPROJECT if path == "pyproject.toml" else UV_LOCK) + b"# drift\n")
    head = fx.commit("pr: unanchored dependency change")
    record = _run(fx, fx.fork_point, head)
    assert (record["status"], record["reason_code"]) == ("FAIL", tdc.DRIFT)


def test_change_after_main_moved_is_drift_not_untouched(fx: Fixture) -> None:
    fx.write("pyproject.toml", PYPROJECT + b"# main moved\n")
    main = fx.commit("main: bump")
    fx.branch("pr", fx.fork_point)
    fx.write("pyproject.toml", PYPROJECT + b"# pr\n")
    head = fx.commit("pr: own change")
    record = _run(fx, main, head)
    assert (record["status"], record["reason_code"]) == ("FAIL", tdc.DRIFT)


@pytest.mark.parametrize("change", ["delete", "symlink"])
def test_deleted_or_symlinked_dependency_file_is_drift(fx: Fixture, change: str) -> None:
    fx.branch("pr", fx.fork_point)
    target = fx.work / "uv.lock"
    target.unlink()
    if change == "symlink":
        target.symlink_to("README.md")
    head = fx.commit(f"pr: {change} uv.lock")
    record = _run(fx, fx.fork_point, head)
    assert (record["status"], record["reason_code"]) == ("FAIL", tdc.DRIFT)


def test_anchor_is_not_honoured_when_main_moved_the_file_since_the_fork(
    fx: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Codex review: main and the PR edit different parts of pyproject.toml, so a
    # three-way merge would yield bytes that match neither anchored snapshot.
    base = b"[project]\nname = 'fixture'\n\n\n\n\nversion = '0'\n"
    fx.write("pyproject.toml", base)
    fork = fx.commit("main: base layout")
    main_bytes = base.replace(b"version = '0'", b"version = '1'")
    fx.write("pyproject.toml", main_bytes)
    main = fx.commit("main: moved pyproject after the fork")
    fx.branch("pr", fork)
    head_bytes = base.replace(b"name = 'fixture'", b"name = 'fixture'\ndependencies = ['x']")
    fx.write("pyproject.toml", head_bytes)
    head = fx.commit("pr: dependency change")
    _authorize(monkeypatch, PR, _hashes((main_bytes, UV_LOCK), (head_bytes, UV_LOCK)))
    record = _run(fx, main, head)
    assert (record["status"], record["reason_code"]) == ("FAIL", tdc.DRIFT)
    # Same anchor shape, main unmoved since the fork: honoured.
    _authorize(monkeypatch, PR, _hashes((base, UV_LOCK), (head_bytes, UV_LOCK)))
    assert _run(fx, fork, head)["reason_code"] == tdc.AUTHORIZED


def test_untouched_requires_every_pr_commit_untouched_not_just_head(fx: Fixture) -> None:
    # Opus review: PR1 = M->C sets main's new bytes; PR2 = C->D reverts them. Head D
    # equals the merge-base M, but once PR1 lands as a merge commit the effective
    # merge-base becomes C and merging D would downgrade the file on main.
    new_bytes = PYPROJECT + b"# legitimate bump\n"
    fx.write("pyproject.toml", new_bytes)
    main = fx.commit("main: legitimate bump W")
    fx.branch("pr1", fx.fork_point)
    fx.write("pyproject.toml", new_bytes)
    c = fx.commit("pr1: C adopts main's bytes")
    fx.branch("pr2", c)
    fx.write("pyproject.toml", PYPROJECT)
    d = fx.commit("pr2: D reverts to the old bytes")
    assert _run(fx, main, c)["reason_code"] == tdc.UNCHANGED
    record = _run(fx, main, d)
    assert record["merge_base_sha"] == fx.fork_point
    assert (record["status"], record["reason_code"]) == ("FAIL", tdc.DRIFT)
    # Prove the attack the rule closes: after PR1 merges with --no-ff, merging D
    # really would put the old bytes on main.
    fx.branch("main-after", main)
    _git(fx.work, "merge", "-q", "--no-ff", "-m", "merge pr1", c)
    landed = _git(fx.work, "rev-parse", "HEAD")
    tree = _git(fx.work, "merge-tree", "--write-tree", landed, d)
    assert _git(fx.work, "cat-file", "blob", f"{tree}:pyproject.toml") == PYPROJECT.decode().strip()


def test_edit_and_revert_while_main_moved_is_drift(fx: Fixture) -> None:
    fx.write("pyproject.toml", PYPROJECT + b"# main moved\n")
    main = fx.commit("main: bump")
    fx.branch("pr", fx.fork_point)
    fx.write("pyproject.toml", PYPROJECT + b"# temporary\n")
    fx.commit("pr: edit")
    fx.write("pyproject.toml", PYPROJECT)
    head = fx.commit("pr: revert")
    assert _run(fx, main, head)["reason_code"] == tdc.DRIFT


def test_catching_up_to_an_older_main_fails_closed_until_latest_main_is_merged(
    fx: Fixture,
) -> None:
    # The every-commit rule is deliberately conservative: a PR commit that predates
    # the catch-up merge carries different entries, so the check fails closed and
    # the remedy ("merge origin/main") makes the bytes identical to main.
    fx.write("uv.lock", UV_LOCK + b"# w1\n")
    w1 = fx.commit("main: w1")
    fx.write("uv.lock", UV_LOCK + b"# w2\n")
    main = fx.commit("main: w2")
    fx.branch("pr", fx.fork_point)
    fx.write("README.md", b"changed\n")
    fx.commit("pr: docs")
    _git(fx.work, "merge", "-q", "--no-ff", "-m", "pr: catch up to w1", w1)
    head = _git(fx.work, "rev-parse", "HEAD")
    record = _run(fx, main, head)
    assert (record["merge_base_sha"], record["reason_code"]) == (w1, tdc.DRIFT)
    _git(fx.work, "merge", "-q", "--no-ff", "-m", "pr: merge latest main", main)
    head = _git(fx.work, "rev-parse", "HEAD")
    assert _run(fx, main, head)["reason_code"] == tdc.UNCHANGED


def test_mode_change_with_identical_bytes_is_drift(fx: Fixture) -> None:
    fx.branch("pr", fx.fork_point)
    (fx.work / "uv.lock").chmod(0o755)
    head = fx.commit("pr: make uv.lock executable")
    assert "100755" in _git(fx.work, "ls-tree", head, "--", "uv.lock")
    assert _run(fx, fx.fork_point, head)["reason_code"] == tdc.DRIFT


def test_anchor_for_another_pr_number_is_drift(
    fx: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    new_pyproject = PYPROJECT + b"dependencies = ['x==1']\n"
    fx.branch("pr", fx.fork_point)
    fx.write("pyproject.toml", new_pyproject)
    head = fx.commit("pr: dependency change")
    _authorize(monkeypatch, PR + 1, _hashes((PYPROJECT, UV_LOCK), (new_pyproject, UV_LOCK)))
    assert _run(fx, fx.fork_point, head)["reason_code"] == tdc.DRIFT


def test_anchor_with_any_hash_mismatch_is_drift(
    fx: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    new_pyproject = PYPROJECT + b"dependencies = ['x==1']\n"
    fx.branch("pr", fx.fork_point)
    fx.write("pyproject.toml", new_pyproject)
    head = fx.commit("pr: dependency change")
    exact = _hashes((PYPROJECT, UV_LOCK), (new_pyproject, UV_LOCK))
    for index in range(4):
        tampered = list(exact)
        tampered[index] = "0" * 64
        _authorize(monkeypatch, PR, tuple(tampered))
        assert _run(fx, fx.fork_point, head)["reason_code"] == tdc.DRIFT


def test_anchor_requires_regular_product_init_like_the_controller(
    fx: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    new_pyproject = PYPROJECT + b"dependencies = ['x==1']\n"
    fx.branch("pr", fx.fork_point)
    fx.write("pyproject.toml", new_pyproject)
    (fx.work / "product/__init__.py").unlink()
    head = fx.commit("pr: dependency change without product/__init__.py")
    _authorize(monkeypatch, PR, _hashes((PYPROJECT, UV_LOCK), (new_pyproject, UV_LOCK)))
    assert _run(fx, fx.fork_point, head)["reason_code"] == tdc.DRIFT


def test_real_anchor_table_admits_nothing_for_an_unknown_transition(fx: Fixture) -> None:
    fx.branch("pr", fx.fork_point)
    fx.write("pyproject.toml", PYPROJECT + b"# drift\n")
    head = fx.commit("pr: drift")
    fx.publish(fx.fork_point, head)
    repo = fx.controller_repo(fx.fork_point)
    for number in (833, 2108, 2114, 2122):
        event = _event(fx.fork_point, head)
        event["pull_request"]["number"] = number
        assert tdc.evaluate(repo, tdc.identity(event))["reason_code"] == tdc.DRIFT


# ----------------------------------------------------------------- fail closed


def test_non_unique_merge_base_fails_closed(fx: Fixture) -> None:
    fx.branch("a", fx.fork_point)
    fx.write("a.txt", b"a\n")
    a1 = fx.commit("a1")
    fx.branch("b", fx.fork_point)
    fx.write("b.txt", b"b\n")
    b1 = fx.commit("b1")
    # Criss-cross: main merges b1 into a1, the PR merges a1 into b1.
    fx.branch("main2", a1)
    _git(fx.work, "merge", "-q", "--no-ff", "-m", "main merge", b1)
    fx.write("pyproject.toml", PYPROJECT + b"# main moved\n")
    main = fx.commit("main: bump")
    fx.branch("pr", b1)
    _git(fx.work, "merge", "-q", "--no-ff", "-m", "pr merge", a1)
    head = _git(fx.work, "rev-parse", "HEAD")
    with pytest.raises(tdc.ContractError, match="MERGE_BASE_NOT_UNIQUE"):
        _run(fx, main, head)


def test_trusted_side_must_hold_regular_dependency_files(fx: Fixture) -> None:
    (fx.work / "uv.lock").unlink()
    main = fx.commit("main: lock removed")
    with pytest.raises(tdc.ContractError, match="trusted default branch"):
        _run(fx, main, main)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda e: e.update(event_name="pull_request"), "workflow identity"),
        (
            lambda e: e.update(
                workflow_ref=f"{REPOSITORY}/.github/workflows/trusted-deletion-anchor.yml"
                "@refs/heads/main"
            ),
            "workflow identity",
        ),
        (
            lambda e: e.update(workflow_ref=f"{REPOSITORY}/{tdc.WORKFLOW_PATH}@refs/heads/feature"),
            "workflow identity",
        ),
        (lambda e: e["pull_request"]["base"].update(ref="release"), "default branch"),
        (
            lambda e: e["pull_request"]["base"]["repo"].update(full_name="evil/fork"),
            "default branch",
        ),
        (lambda e: e["pull_request"].update(number="4242"), "positive integer"),
        (lambda e: e["pull_request"].update(number=True), "positive integer"),
        (lambda e: e["pull_request"]["head"].update(sha="HEAD"), "exact SHA"),
        (lambda e: e.update(workflow_sha="a" * 39), "exact SHA"),
        (lambda e: e.pop("workflow_sha"), "exact SHA"),
    ],
)
def test_identity_fails_closed(mutate: Any, message: str) -> None:
    event = _event("a" * 40, "b" * 40)
    mutate(event)
    with pytest.raises(tdc.ContractError, match=message):
        tdc.identity(event)


def test_cli_exit_codes_and_output(fx: Fixture, tmp_path: Path, capsys) -> None:
    fx.branch("pr", fx.fork_point)
    fx.write("uv.lock", UV_LOCK + b"# drift\n")
    head = fx.commit("pr: drift")
    fx.publish(fx.fork_point, head)
    repo = fx.controller_repo(fx.fork_point)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(_event(fx.fork_point, head)), encoding="utf-8")
    output = tmp_path / "result.json"
    argv = ["check", "--event-json", str(event_path), "--repo-root", str(repo)]
    assert tdc.main([*argv, "--output", str(output)]) == 1
    assert json.loads(output.read_text())["reason_code"] == tdc.DRIFT
    assert f"{tdc.DRIFT}: PR #{PR}" in capsys.readouterr().err
    bad = _event(fx.fork_point, head, event_name="pull_request")
    event_path.write_text(json.dumps(bad), encoding="utf-8")
    assert tdc.main(argv) == 1
    assert "failed closed" in capsys.readouterr().err


def test_log_detail_defuses_workflow_commands() -> None:
    assert "##[" not in tdc._log_detail("x\n##[error]injected\n::set-output name=a::b")
    assert "\n" not in tdc._log_detail("a\nb")


# ----------------------------------------------------------------- workflow contract


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _step(name: str) -> dict[str, Any]:
    return next(step for step in _workflow()["jobs"][JOB]["steps"] if step.get("name") == name)


def test_workflow_is_one_isolated_default_branch_job() -> None:
    workflow = _workflow()
    trigger = workflow.get("on", workflow.get(True))
    assert set(trigger) == {"pull_request_target"}
    assert trigger["pull_request_target"]["branches"] == ["main"]
    assert workflow["permissions"] == {}
    assert set(workflow["jobs"]) == {JOB}
    job = workflow["jobs"][JOB]
    assert job["name"] == "Trusted dependency contract (default branch)"
    assert job["permissions"] == {"contents": "read"}
    assert "needs" not in job and "if" not in job
    assert "continue-on-error" not in json.dumps(job)
    text = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in (
        "actions/checkout",
        "git checkout",
        "git worktree",
        "git submodule",
        "pull_request.body",
        "pull_request.title",
        "head.ref",
        "trusted_merge_lane_gate",
        "secrets.",
        "credential.helper",
        "persist-credentials",
    ):
        assert forbidden not in text, forbidden
    run = _step(STEP)["run"]
    assert '"$REPOSITORY/$workflow_path@refs/heads/$DEFAULT_BRANCH"' in run
    assert "workflow_path='.github/workflows/trusted-dependency-contract.yml'" in run
    assert 'git -C "$bare_repo" cat-file blob "$blob_id"' in run
    assert 'python -I -B "$trusted_dir/scripts/ops/trusted_dependency_contract.py" check' in run
    assert job["steps"][-1]["if"] == "always()"


def _shell(
    fx: Fixture, main_sha: str, head_sha: str, run_root: Path
) -> subprocess.CompletedProcess:
    fx.publish(main_sha, head_sha)
    run = _step(STEP)["run"].replace(
        '"https://github.com/$REPOSITORY.git"', shlex.quote(fx.origin.as_uri())
    )
    event = _event(main_sha, head_sha)
    run_root.mkdir()
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(run_root),
        "GITHUB_STEP_SUMMARY": str(run_root / "summary.md"),
        "EVENT_JSON": json.dumps(event),
        "EVENT_NAME": "pull_request_target",
        "WORKFLOW_REF": event["workflow_ref"],
        "WORKFLOW_SHA": main_sha,
        "RUN_ID": "7",
        "REPOSITORY": REPOSITORY,
        "DEFAULT_BRANCH": "main",
        "TRUSTED_TOKEN": "token-must-not-leak",
    }
    return subprocess.run(["bash", "-c", run], env=env, capture_output=True, text=True)


def _trusted_main(fx: Fixture) -> str:
    for path in (
        "scripts/__init__.py",
        "scripts/ops/__init__.py",
        "scripts/ops/trusted_deletion_anchor.py",
        "scripts/ops/trusted_dependency_contract.py",
    ):
        fx.write(path, (ROOT / path).read_bytes())
    return fx.commit("main: trusted sources")


def test_workflow_shell_runs_only_default_branch_code(fx: Fixture, tmp_path: Path) -> None:
    main = _trusted_main(fx)
    fx.branch("pr", main)
    marker = tmp_path / "head-code-executed"
    # A hostile head replaces the checker with code that would pass and leave a marker.
    fx.write(
        "scripts/ops/trusted_dependency_contract.py",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n".encode(),
    )
    fx.write("pyproject.toml", PYPROJECT + b"# drift\n")
    head = fx.commit("pr: hostile checker plus drift")
    completed = _shell(fx, main, head, tmp_path / "run")
    assert completed.returncode == 1, completed.stderr
    assert not marker.exists()
    assert tdc.DRIFT in completed.stderr
    assert "token-must-not-leak" not in completed.stdout + completed.stderr
    summary = (tmp_path / "run/summary.md").read_text(encoding="utf-8")
    assert f'"reason_code":"{tdc.DRIFT}"' in summary


def test_workflow_shell_passes_untouched_pr(fx: Fixture, tmp_path: Path) -> None:
    main = _trusted_main(fx)
    fx.branch("pr", main)
    fx.write("README.md", b"changed\n")
    head = fx.commit("pr: docs only")
    completed = _shell(fx, main, head, tmp_path / "run")
    assert completed.returncode == 0, completed.stderr
    assert f'"reason_code":"{tdc.UNCHANGED}"' in completed.stdout


def test_workflow_shell_runs_the_merge_base_path_when_main_moved(
    fx: Fixture, tmp_path: Path
) -> None:
    main = _trusted_main(fx)
    fx.write("pyproject.toml", PYPROJECT + b"# main moved\n")
    moved = fx.commit("main: bump after the fork")
    fx.branch("pr", main)
    fx.write("README.md", b"changed\n")
    head = fx.commit("pr: docs only")
    completed = _shell(fx, moved, head, tmp_path / "run")
    assert completed.returncode == 0, completed.stderr
    assert f'"reason_code":"{tdc.UNTOUCHED}"' in completed.stdout
    assert f'"merge_base_sha":"{main}"' in completed.stdout
    assert "::add-mask::" in completed.stdout


def test_workflow_shell_rejects_non_default_branch_workflow_ref(
    fx: Fixture, tmp_path: Path
) -> None:
    main = _trusted_main(fx)
    fx.publish(main, main)
    run = _step(STEP)["run"].replace(
        '"https://github.com/$REPOSITORY.git"', shlex.quote(fx.origin.as_uri())
    )
    run_root = tmp_path / "run"
    run_root.mkdir()
    env = {
        **os.environ,
        "RUNNER_TEMP": str(run_root),
        "GITHUB_STEP_SUMMARY": str(run_root / "summary.md"),
        "EVENT_JSON": json.dumps(_event(main, main)),
        "EVENT_NAME": "pull_request_target",
        "WORKFLOW_REF": f"{REPOSITORY}/{tdc.WORKFLOW_PATH}@refs/heads/pr",
        "WORKFLOW_SHA": main,
        "RUN_ID": "7",
        "REPOSITORY": REPOSITORY,
        "DEFAULT_BRANCH": "main",
        "TRUSTED_TOKEN": "t",
    }
    completed = subprocess.run(["bash", "-c", run], env=env, capture_output=True, text=True)
    assert completed.returncode != 0
    assert "default-branch workflow" in completed.stderr
    assert not (run_root / "trusted-dependency-contract-source").exists()
