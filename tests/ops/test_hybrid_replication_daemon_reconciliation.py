from __future__ import annotations

from typing import Any

import scripts.ops.hybrid_replication_daemon as daemon

BOUNDARY = "2026-10-02T02:36:35Z"


def _issue(*, number: int, created_at: str, updated_at: str) -> dict[str, Any]:
    return {
        "number": number,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def test_issues_since_ignores_pre_boundary_non_edit_updates(monkeypatch) -> None:
    issue = _issue(
        number=1275,
        created_at="2026-10-01T03:43:31Z",
        updated_at="2026-10-02T02:39:56Z",
    )
    calls: list[tuple[str, ...]] = []

    def fake_gh_json(*args: str) -> Any:
        calls.append(args)
        if args[0] == "-X":
            return [issue]
        raise AssertionError(args)

    monkeypatch.setattr(daemon, "_gh_json", fake_gh_json)

    assert daemon._issues_since("James3014/Nexus-new", BOUNDARY) == []
    assert all(args[0] != "graphql" for args in calls)


def test_issues_since_keeps_pre_boundary_issue_edited_after_boundary(monkeypatch) -> None:
    issue = _issue(
        number=1200,
        created_at="2026-10-01T03:00:00Z",
        updated_at="2026-10-02T02:38:00Z",
    )

    def fake_gh_json(*args: str) -> Any:
        if args[0] == "-X":
            return [issue]
        raise AssertionError(args)

    monkeypatch.setattr(daemon, "_gh_json", fake_gh_json)

    assert daemon._issues_since("James3014/Nexus-new", BOUNDARY) == []


def test_issues_since_keeps_post_boundary_open_without_graphql(monkeypatch) -> None:
    issue = _issue(
        number=1400,
        created_at="2026-10-02T02:37:00Z",
        updated_at="2026-10-02T02:37:00Z",
    )

    def fake_gh_json(*args: str) -> Any:
        if args[0] == "-X":
            return [issue]
        raise AssertionError("post-boundary opening should not need GraphQL")

    monkeypatch.setattr(daemon, "_gh_json", fake_gh_json)

    assert daemon._issues_since("James3014/Nexus-new", BOUNDARY) == [issue]


def _run_ingest_only(monkeypatch, tmp_path, issues, comments_by_number) -> tuple[int, dict]:
    import io
    import json
    import sys
    from contextlib import redirect_stdout

    monkeypatch.setattr(daemon, "CANDIDATE_REPOSITORIES", ("James3014/Nexus-new",))
    monkeypatch.setattr(daemon, "_issues_since", lambda repository, since: issues)
    monkeypatch.setattr(
        daemon, "_comments", lambda repository, number: comments_by_number.get(number, [])
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["d", "--root", str(tmp_path), "--since", BOUNDARY, "--ingest-only"],
    )
    out = io.StringIO()
    with redirect_stdout(out):
        code = daemon.main()
    report = json.loads(out.getvalue().split("\n}\n")[0] + "\n}")
    return code, report


def _authored(number: int, login: str) -> dict[str, Any]:
    return {
        **_issue(
            number=number, created_at="2026-10-13T11:28:26Z", updated_at="2026-10-13T11:28:26Z"
        ),
        "user": {"login": login},
    }


def test_github_token_bot_issue_without_capture_is_not_missing(monkeypatch, tmp_path) -> None:
    for login in ("github-actions[bot]", "app/github-actions"):
        code, report = _run_ingest_only(
            monkeypatch, tmp_path / login.replace("/", "_"), [_authored(2055, login)], {}
        )
        assert code == 0
        assert report["missing_capture"] == []
        assert report["not_captured_github_token_issue"] == ["James3014/Nexus-new#2055"]
        assert report["expected_count"] == 0


def test_owner_issue_without_capture_is_still_missing(monkeypatch, tmp_path) -> None:
    code, report = _run_ingest_only(monkeypatch, tmp_path, [_authored(2056, "James3014")], {})
    assert code == 3
    assert report["missing_capture"] == ["James3014/Nexus-new#2056"]
    assert report["not_captured_github_token_issue"] == []


def test_github_token_bot_issue_with_capture_is_mirrored(monkeypatch, tmp_path) -> None:
    from nexus.research.hybrid_replication_pipeline import TaskSnapshot, build_capture_comment

    snapshot = TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=2057,
        created_at="2026-10-13T11:28:26Z",
        captured_at="2026-10-13T11:28:30Z",
        issue_updated_at="2026-10-13T11:28:26Z",
        title="bot issue",
        body="body",
        pre_implementation_revision="a" * 40,
        default_branch="main",
        source_event_id="actions:1:1",
    )
    code, report = _run_ingest_only(
        monkeypatch,
        tmp_path,
        [_authored(2057, "github-actions[bot]")],
        {2057: [{"body": build_capture_comment(snapshot)}]},
    )
    assert report["missing_capture"] == []
    assert report["not_captured_github_token_issue"] == []
    assert report["expected_count"] == 1
    assert report["mirrored_count"] == 1
