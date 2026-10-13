"""Hermetic tests for the read-only Gateway source drift check (#1900)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.ops import check_gateway_source_drift as drift

HOUR = 3600
T0 = 1_760_000_000


class Repo:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.mkdir()
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str, when: int = T0) -> str:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "GIT_AUTHOR_DATE": f"@{when} +0000",
            "GIT_COMMITTER_DATE": f"@{when} +0000",
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(self.path),
        }
        return subprocess.run(
            ["git", "-C", str(self.path), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout.strip()

    def commit(self, rel: str, *, when: int = T0) -> str:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{rel}@{when}\n{target.read_text() if target.exists() else ''}")
        self.git("add", rel)
        self.git("commit", "-q", "-m", rel, when=when)
        return self.git("rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path / "clone")
    r.commit("README.md")
    return r


def health(head: str, **extra: object) -> dict[str, object]:
    return {"git_head": head, "repo_head_current": head, "reload_required": False, **extra}


def deploy_branch(repo: Repo, base: str, *files: str, when: int = T0) -> str:
    repo.git("checkout", "-q", "-b", "deploy", base)
    head = base
    for rel in files:
        head = repo.commit(rel, when=when)
    repo.git("checkout", "-q", "main")
    return head


def run(
    repo: Repo,
    payload: object,
    capsys: pytest.CaptureFixture[str],
    *,
    pr_heads: dict[str, list[int]] | None = None,
) -> tuple[int, dict]:
    def fetch(_url: str) -> object:
        if isinstance(payload, Exception):
            raise payload
        return payload

    lookups: dict[str, list[int]] = pr_heads or {}
    code = drift.main(
        ["--repo", str(repo.path), "--main-ref", "main", "--json"],
        fetch_health=fetch,
        pr_head_lookup=lambda sha: lookups.get(sha, []),
    )
    return code, json.loads(capsys.readouterr().out)


def codes(report: dict) -> list[str]:
    return [f["code"] for f in report["findings"]]


def advance_main(repo: Repo, count: int, *, start: int = T0 + HOUR, step: int = 60) -> None:
    for i in range(count):
        repo.commit(f"docs/n{i}.md", when=start + i * step)


def test_in_sync_is_ok(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    head = repo.git("rev-parse", "HEAD")
    code, report = run(repo, health(head), capsys)
    assert (code, report["verdict"], report["findings"]) == (0, "OK", [])
    assert report["published_base"] == head and report["pr_head_lookup"] == "NOT_NEEDED"


def test_task_only_unpublished_commits_still_alert(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """Owner refinement 2026-10-13T02:09:54Z: tasks/**-only unpublished commits are INFO.

    The test id is kept stable for the exact-base impact gate; it no longer alerts.
    """
    base = repo.git("rev-parse", "HEAD")
    head = deploy_branch(repo, base, "tasks/issue-1384/a.md", "tasks/issue-1384/b.json")
    code, report = run(repo, health(head), capsys)
    assert code == 0 and report["verdict"] == "INFO"
    assert codes(report) == ["GATEWAY_BIND_ONLY_LOCAL_COMMITS(2)"]
    finding = report["findings"][0]
    assert finding["touched_paths"] == ["tasks/issue-1384/a.md", "tasks/issue-1384/b.json"]
    assert finding["touched_paths_outside_tasks"] == []
    assert report["published_base"] == base and report["pr_head_lookup"] == "NO_MATCH"
    assert "#1939" in report["summary"]


def test_bind_only_with_behind_main_warn_keeps_warn(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    base = repo.git("rev-parse", "HEAD")
    head = deploy_branch(repo, base, "tasks/t.md")
    advance_main(repo, 60)
    code, report = run(repo, health(head), capsys)
    assert code == 1 and report["verdict"] == "WARN"
    assert codes(report) == ["GATEWAY_BIND_ONLY_LOCAL_COMMITS(1)", "GATEWAY_BEHIND_MAIN(60)"]


def test_merge_commit_is_judged_by_first_parent_diff(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    base = repo.git("rev-parse", "HEAD")
    # Side branch carries code, but it is merged from main's side: the merge's
    # first-parent diff is what counts, and the side commit is itself unpublished.
    repo.git("checkout", "-q", "-b", "deploy", base)
    repo.commit("tasks/local.md")
    repo.git("checkout", "-q", "main")
    repo.commit("nexus/published.py", when=T0 + 10)  # published on main
    repo.git("checkout", "-q", "deploy")
    repo.git("merge", "-q", "--no-ff", "-m", "merge main", "main", when=T0 + 20)
    head = repo.git("rev-parse", "HEAD")
    repo.git("checkout", "-q", "main")
    code, report = run(repo, health(head), capsys)
    # The merge changes nexus/published.py relative to first parent, but that file
    # is on main; only the merge commit and tasks commit are unpublished.
    finding = report["findings"][0]
    assert finding["touched_paths"] == ["nexus/published.py", "tasks/local.md"]
    assert code == 1 and codes(report)[0] == "GATEWAY_SOURCE_UNPUBLISHED(2)"


def test_merge_of_tasks_only_branches_is_bind_only(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    base = repo.git("rev-parse", "HEAD")
    repo.git("checkout", "-q", "-b", "deploy", base)
    repo.commit("tasks/a.md")
    repo.git("checkout", "-q", "-b", "side", base)
    repo.commit("tasks/b.md", when=T0 + 5)
    repo.git("checkout", "-q", "deploy")
    repo.git("merge", "-q", "--no-ff", "-m", "merge side", "side", when=T0 + 20)
    head = repo.git("rev-parse", "HEAD")
    repo.git("checkout", "-q", "main")
    code, report = run(repo, health(head), capsys)
    assert code == 0 and codes(report) == ["GATEWAY_BIND_ONLY_LOCAL_COMMITS(3)"]
    assert report["findings"][0]["touched_paths"] == ["tasks/a.md", "tasks/b.md"]


def test_code_in_unpublished_commits_alerts(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.git("rev-parse", "HEAD")
    head = deploy_branch(repo, base, "tasks/x.md", "nexus/foo.py")
    code, report = run(repo, health(head), capsys)
    assert code == 1 and codes(report) == ["GATEWAY_SOURCE_UNPUBLISHED(2)"]
    assert report["findings"][0]["touched_paths_outside_tasks"] == ["nexus/foo.py"]


def test_exact_published_pr_head_is_allowed(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.git("rev-parse", "HEAD")
    head = deploy_branch(repo, base, "nexus/foo.py")
    code, report = run(repo, health(head), capsys, pr_heads={head: [1234]})
    assert code == 0 and report["verdict"] == "INFO"
    assert codes(report) == ["GATEWAY_PUBLISHED_PR_HEAD(#1234)"]


def test_pr_containing_head_but_other_tip_is_not_allowed(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    base = repo.git("rev-parse", "HEAD")
    head = deploy_branch(repo, base, "nexus/foo.py")
    code, report = run(repo, health(head), capsys, pr_heads={"e" * 40: [1]})
    assert code == 1 and codes(report) == ["GATEWAY_SOURCE_UNPUBLISHED(1)"]


def test_offline_skips_pr_lookup_and_alerts(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.git("rev-parse", "HEAD")
    head = deploy_branch(repo, base, "nexus/t.py")

    def lookup(_sha: str) -> list[int]:
        raise AssertionError("lookup must not run with --offline")

    code = drift.main(
        ["--repo", str(repo.path), "--main-ref", "main", "--json", "--offline"],
        fetch_health=lambda _u: health(head),
        pr_head_lookup=lookup,
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 1 and report["pr_head_lookup"] == "SKIPPED_OFFLINE"


def test_behind_within_budget_is_ok(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    head = repo.git("rev-parse", "HEAD")
    advance_main(repo, drift.BEHIND_MAX_COMMITS)
    code, report = run(repo, health(head), capsys)
    assert code == 0 and report["verdict"] == "OK" and report["findings"] == []
    assert report["behind_main"] == 50


def test_behind_more_than_50_commits_warns(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    head = repo.git("rev-parse", "HEAD")
    advance_main(repo, drift.BEHIND_MAX_COMMITS + 1)
    code, report = run(repo, health(head), capsys)
    assert code == 1 and report["verdict"] == "WARN"
    assert codes(report) == ["GATEWAY_BEHIND_MAIN(51)"]
    assert report["findings"][0]["reasons"] == ["MORE_THAN_50_COMMITS"]


def test_behind_more_than_7_days_warns(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    head = repo.git("rev-parse", "HEAD")
    repo.commit("docs/later.md", when=T0 + 7 * 24 * HOUR + 1)
    code, report = run(repo, health(head), capsys)
    assert code == 1 and codes(report) == ["GATEWAY_BEHIND_MAIN(1)"]
    assert report["findings"][0]["reasons"] == ["MORE_THAN_7_DAYS"]


def test_exactly_7_days_behind_is_ok(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    head = repo.git("rev-parse", "HEAD")
    repo.commit("docs/later.md", when=T0 + 7 * 24 * HOUR)
    code, report = run(repo, health(head), capsys)
    assert code == 0 and report["findings"] == []


def test_unpublished_and_behind_reports_both(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    base = repo.git("rev-parse", "HEAD")
    head = deploy_branch(repo, base, "nexus/t.py")
    advance_main(repo, 60)
    code, report = run(repo, health(head), capsys)
    assert code == 1 and report["verdict"] == "ALERT"
    assert codes(report) == ["GATEWAY_SOURCE_UNPUBLISHED(1)", "GATEWAY_BEHIND_MAIN(60)"]


def test_unreachable_health_fails_closed(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    code, report = run(repo, ConnectionRefusedError("refused"), capsys)
    assert code == 2 and report["verdict"] == "PROBE_FAILURE"
    assert codes(report) == ["GATEWAY_HEALTH_UNREACHABLE"]


@pytest.mark.parametrize(
    "payload",
    [["not", "object"], {"git_head": "abc"}, {"status": "ok"}, json.JSONDecodeError("bad", "x", 0)],
)
def test_malformed_health_fails_closed(
    repo: Repo, capsys: pytest.CaptureFixture[str], payload: object
) -> None:
    code, report = run(repo, payload, capsys)
    assert code == 2 and codes(report) == ["GATEWAY_HEALTH_MALFORMED"]


def test_unknown_head_fails_closed(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    code, report = run(repo, health("f" * 40), capsys)
    assert code == 2 and codes(report) == ["GATEWAY_HEAD_UNRESOLVABLE"]


def test_head_is_fetched_from_deployment_source(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deployment = Repo(tmp_path / "deployment")
    deployment.git("fetch", "-q", str(repo.path), "main")
    deployment.git("checkout", "-q", "FETCH_HEAD")
    head = deployment.commit("nexus/local.py")
    code, report = run(repo, health(head, repo_root=str(deployment.path)), capsys)
    assert code == 1 and codes(report) == ["GATEWAY_SOURCE_UNPUBLISHED(1)"]


def test_gh_pr_head_lookup_requires_exact_head_and_open_or_merged() -> None:
    sha = "a" * 40
    listing = [
        {"number": 1, "headRefOid": sha, "state": "MERGED"},
        {"number": 2, "headRefOid": sha, "state": "OPEN"},
        {"number": 3, "headRefOid": sha, "state": "CLOSED"},
        {"number": 4, "headRefOid": "b" * 40, "state": "OPEN"},
    ]
    seen: list[list[str]] = []

    def gh(args, _stdin):
        seen.append(list(args))
        return json.dumps(listing)

    assert drift.gh_pr_head_lookup("o/r", gh)(sha) == [1, 2]
    assert seen[0][:4] == ["pr", "list", "-R", "o/r"]


def test_pr_lookup_failure_fails_closed(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.git("rev-parse", "HEAD")
    head = deploy_branch(repo, base, "tasks/t.md")

    def gh(_args, _stdin):
        raise drift.ProbeError("REPORT_FAILED", "gh down")

    code = drift.main(
        ["--repo", str(repo.path), "--main-ref", "main", "--json"],
        fetch_health=lambda _u: health(head),
        gh=gh,
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 2 and codes(report) == ["PR_LOOKUP_FAILED"]


def test_report_issue_updates_existing_marker_comment(repo: Repo) -> None:
    calls: list[tuple[list[str], str | None]] = []

    def gh(args, stdin):
        calls.append((list(args), stdin))
        if "--paginate" in args:
            return "\n".join(
                json.dumps(c)
                for c in (
                    {"id": 1, "body": "unrelated"},
                    {"id": 7, "body": f"{drift.REPORT_MARKER}\nold"},
                )
            )
        return "{}"

    report = {"verdict": "OK", "findings": []}
    assert drift.report_to_issue(report, 1900, "o/r", gh) == "updated"
    assert calls[-1][0][:4] == ["api", "-X", "PATCH", "repos/o/r/issues/comments/7"]
    assert drift.REPORT_MARKER in json.loads(calls[-1][1] or "{}")["body"]


def test_report_issue_creates_when_no_marker(repo: Repo) -> None:
    calls: list[list[str]] = []

    def gh(args, _stdin):
        calls.append(list(args))
        return json.dumps({"id": 1, "body": "unrelated"}) if "--paginate" in args else "{}"

    assert drift.report_to_issue({"verdict": "OK", "findings": []}, 1900, "o/r", gh) == "created"
    assert calls[-1][:4] == ["api", "-X", "POST", "repos/o/r/issues/1900/comments"]


def test_no_report_without_flag(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    head = repo.git("rev-parse", "HEAD")

    def gh(_args, _stdin):
        raise AssertionError("gh must not be called without --report-issue")

    args = ["--repo", str(repo.path), "--main-ref", "main"]
    assert drift.main(args, fetch_health=lambda _u: health(head), gh=gh) == 0
    assert capsys.readouterr().out.startswith("gateway-source-drift OK")
