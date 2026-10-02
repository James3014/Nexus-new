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


def test_issues_since_ignores_pre_boundary_issue_edited_after_boundary(monkeypatch) -> None:
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
