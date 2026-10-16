from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from nexus.research.hybrid_replication_pipeline import (
    AdmissionReceipt,
    AutomaticReplicationStore,
    TaskSnapshot,
    build_admission_comment,
    build_capture_comment,
)
from scripts.ops import hybrid_replication_daemon as daemon

REPO = "James3014/Nexus-new"
REPO_B = "James3014/devspace"
T0 = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
UPDATED = "2026-10-15T11:00:00Z"


def _issue(number: int = 7, updated_at: str | None = UPDATED, **extra: Any) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "number": number,
        "created_at": "2026-10-07T12:00:00Z",
        "comments": 1,
        **extra,
    }
    if updated_at is not None:
        issue["updated_at"] = updated_at
    return issue


class _Fetcher:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[str, int]] = []
        monkeypatch.setattr(daemon, "_comments", self)

    def __call__(self, repository: str, number: int) -> list[dict[str, Any]]:
        self.calls.append((repository, number))
        return [{"body": f"fetch-{len(self.calls)}"}]


def _cache_file(root: Path, number: int = 7) -> Path:
    return root / REPO.replace("/", "__") / f"{number}.json"


def test_cache_hit_when_updated_at_unchanged_within_ttl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = _Fetcher(monkeypatch)
    first = daemon._cached_comments(tmp_path, REPO, _issue(), now=T0)
    second = daemon._cached_comments(
        tmp_path, REPO, _issue(), now=T0 + timedelta(seconds=daemon.COMMENT_CACHE_TTL_SECONDS - 1)
    )
    assert first == second == [{"body": "fetch-1"}]
    assert fetch.calls == [(REPO, 7)]
    payload = json.loads(_cache_file(tmp_path).read_text(encoding="utf-8"))
    assert payload == {
        "updated_at": UPDATED,
        "fetched_at": "2026-10-15T12:00:00Z",
        "comment_count": 1,
        "comments": [{"body": "fetch-1"}],
    }


def test_refetch_when_updated_at_changed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fetch = _Fetcher(monkeypatch)
    daemon._cached_comments(tmp_path, REPO, _issue(), now=T0)
    result = daemon._cached_comments(
        tmp_path, REPO, _issue(updated_at="2026-10-15T11:30:00Z"), now=T0
    )
    assert result == [{"body": "fetch-2"}]
    assert len(fetch.calls) == 2


def test_cache_hit_with_equal_comment_count_and_refetch_when_count_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = _Fetcher(monkeypatch)
    daemon._cached_comments(tmp_path, REPO, _issue(comments=3), now=T0)
    daemon._cached_comments(tmp_path, REPO, _issue(comments=3), now=T0)
    assert len(fetch.calls) == 1
    # same updated_at, one comment deleted
    assert daemon._cached_comments(tmp_path, REPO, _issue(comments=2), now=T0) == [
        {"body": "fetch-2"}
    ]
    assert len(fetch.calls) == 2
    daemon._cached_comments(tmp_path, REPO, _issue(comments=2), now=T0)
    assert len(fetch.calls) == 2


@pytest.mark.parametrize("count", ["missing", None, "3", 3.0, True])
def test_refetch_when_listed_comment_count_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: Any
) -> None:
    fetch = _Fetcher(monkeypatch)
    issue = _issue()
    if count == "missing":
        del issue["comments"]
    else:
        issue["comments"] = count
    daemon._cached_comments(tmp_path, REPO, issue, now=T0)
    daemon._cached_comments(tmp_path, REPO, issue, now=T0)
    assert len(fetch.calls) == 2


def test_refetch_when_cached_comment_count_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = _Fetcher(monkeypatch)
    path = _cache_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"updated_at": UPDATED, "fetched_at": "2026-10-15T12:00:00Z", "comments": []}),
        encoding="utf-8",
    )
    daemon._cached_comments(tmp_path, REPO, _issue(), now=T0)
    assert len(fetch.calls) == 1


def test_refetch_when_ttl_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fetch = _Fetcher(monkeypatch)
    daemon._cached_comments(tmp_path, REPO, _issue(), now=T0)
    later = T0 + timedelta(seconds=daemon.COMMENT_CACHE_TTL_SECONDS)
    assert daemon._cached_comments(tmp_path, REPO, _issue(), now=later) == [{"body": "fetch-2"}]
    assert len(fetch.calls) == 2


def test_refetch_when_cached_fetch_time_is_in_the_future(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = _Fetcher(monkeypatch)
    daemon._cached_comments(tmp_path, REPO, _issue(), now=T0)
    daemon._cached_comments(tmp_path, REPO, _issue(), now=T0 - timedelta(seconds=5))
    assert len(fetch.calls) == 2


@pytest.mark.parametrize("updated_at", [None, ""])
def test_refetch_when_issue_has_no_updated_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, updated_at: str | None
) -> None:
    fetch = _Fetcher(monkeypatch)
    daemon._cached_comments(tmp_path, REPO, _issue(updated_at=updated_at), now=T0)
    daemon._cached_comments(tmp_path, REPO, _issue(updated_at=updated_at), now=T0)
    assert len(fetch.calls) == 2


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "",
        "[]",
        "null",
        json.dumps({"updated_at": UPDATED, "comments": []}),
        json.dumps({"updated_at": UPDATED, "fetched_at": "garbage", "comments": []}),
        json.dumps({"updated_at": UPDATED, "fetched_at": 5, "comments": []}),
        json.dumps({
            "updated_at": UPDATED,
            "fetched_at": "2026-10-15T12:00:00Z",
            "comment_count": 1,
            "comments": {},
        }),
        json.dumps({"updated_at": UPDATED, "fetched_at": "2026-10-15T12:00:00Z"}),
        json.dumps({"fetched_at": "2026-10-15T12:00:00Z", "comments": []}),
        json.dumps({"updated_at": UPDATED, "fetched_at": "2026-10-15T12:00:00", "comments": []}),
    ],
)
def test_corrupt_cache_refetches_and_rewrites_valid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    fetch = _Fetcher(monkeypatch)
    path = _cache_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    assert daemon._cached_comments(tmp_path, REPO, _issue(), now=T0) == [{"body": "fetch-1"}]
    assert len(fetch.calls) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["comments"] == [{"body": "fetch-1"}]
    # now valid: a second call is a hit
    daemon._cached_comments(tmp_path, REPO, _issue(), now=T0)
    assert len(fetch.calls) == 1


def test_no_stray_tmp_files_after_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _Fetcher(monkeypatch)
    daemon._cached_comments(tmp_path, REPO, _issue(), now=T0)
    daemon._cached_comments(tmp_path, REPO, _issue(updated_at="2026-10-15T11:31:00Z"), now=T0)
    assert [p.name for p in _cache_file(tmp_path).parent.iterdir()] == ["7.json"]


def test_cache_write_failure_is_best_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _Fetcher(monkeypatch)

    def boom(src: Any, dst: Any) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(daemon.os, "replace", boom)
    assert daemon._cached_comments(tmp_path, REPO, _issue(), now=T0) == [{"body": "fetch-1"}]
    assert list(tmp_path.rglob("*.tmp")) == []
    assert not _cache_file(tmp_path).exists()


def test_cache_dir_creation_failure_is_best_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _Fetcher(monkeypatch)
    blocker = tmp_path / "cache"
    blocker.write_text("a file, not a directory", encoding="utf-8")
    assert daemon._cached_comments(blocker, REPO, _issue(), now=T0) == [{"body": "fetch-1"}]


def test_non_oserror_during_cache_write_propagates_after_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _Fetcher(monkeypatch)

    def boom(src: Any, dst: Any) -> None:
        raise RuntimeError("not an os error")

    monkeypatch.setattr(daemon.os, "replace", boom)
    with pytest.raises(RuntimeError, match="not an os error"):
        daemon._cached_comments(tmp_path, REPO, _issue(), now=T0)
    assert list(tmp_path.rglob("*.tmp")) == []


# ---- terminal resolver -------------------------------------------------------------------


class _CapturingController:
    instances: list["_CapturingController"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.terminal_resolver = kwargs["terminal_resolver"]
        _CapturingController.instances.append(self)


class _FakeResolver:
    def __init__(self, command: str) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, state: dict[str, Any]) -> str:
        self.calls.append(state)
        return "resolved"


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _resolver_for(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    listed: dict[tuple[str, int], str] | None,
    listed_at: float | None = 1000.0,
    clock: _Clock | None = None,
) -> tuple[Any, _FakeResolver]:
    _CapturingController.instances = []
    resolvers: list[_FakeResolver] = []

    def make(command: str) -> _FakeResolver:
        resolvers.append(_FakeResolver(command))
        return resolvers[-1]

    monkeypatch.setattr(daemon, "AutomaticReplicationController", _CapturingController)
    monkeypatch.setattr(daemon, "ExternalFrozenStackRunner", lambda command: object())
    monkeypatch.setattr(daemon, "ExternalGroundTruthResolver", make)
    daemon.advance_all(
        store=AutomaticReplicationStore(tmp_path),
        frozen_policy_sha256="f" * 64,
        stack_command="stack",
        ground_truth_command="gt",
        listed_issue_states=listed,
        listed_at_monotonic=listed_at,
        monotonic=clock or _Clock(),
    )
    return _CapturingController.instances[0].terminal_resolver, resolvers[0]


def _state(repository: str = REPO, number: int = 5) -> dict[str, Any]:
    return {"snapshot": {"repository": repository, "issue_number": number}}


def test_terminal_resolver_skipped_for_listed_open_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver, fake = _resolver_for(tmp_path, monkeypatch, {(REPO, 5): "open"})
    assert resolver(_state()) is None
    assert fake.calls == []


def test_terminal_resolver_called_for_listed_closed_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver, fake = _resolver_for(tmp_path, monkeypatch, {(REPO, 5): "closed"})
    assert resolver(_state()) == "resolved"
    assert len(fake.calls) == 1


def test_terminal_resolver_called_for_unlisted_or_other_state_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = {(REPO, 5): "open", (REPO, 6): "", (REPO, 8): "Open"}
    resolver, fake = _resolver_for(tmp_path, monkeypatch, listed)
    assert resolver(_state(number=9)) == "resolved"
    assert resolver(_state(REPO_B, 5)) == "resolved"
    assert resolver(_state(number=6)) == "resolved"
    assert resolver(_state(number=8)) == "resolved"
    assert resolver({}) == "resolved"
    assert len(fake.calls) == 5


def test_terminal_resolver_called_when_listed_states_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver, fake = _resolver_for(tmp_path, monkeypatch, None)
    assert resolver(_state()) == "resolved"
    assert len(fake.calls) == 1


def test_terminal_resolver_skip_only_while_listing_is_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    resolver, fake = _resolver_for(tmp_path, monkeypatch, {(REPO, 5): "open"}, clock=clock)
    clock.now = 1000.0 + daemon.LISTED_STATE_MAX_AGE_SECONDS
    assert resolver(_state()) is None
    assert fake.calls == []
    clock.now = 1000.0 + daemon.LISTED_STATE_MAX_AGE_SECONDS + 1  # 121 s: stale
    assert resolver(_state()) == "resolved"
    assert len(fake.calls) == 1


def test_terminal_resolver_called_when_listed_at_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver, fake = _resolver_for(tmp_path, monkeypatch, {(REPO, 5): "open"}, listed_at=None)
    assert resolver(_state()) == "resolved"
    assert len(fake.calls) == 1


def test_terminal_resolver_sees_states_recorded_after_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed: dict[tuple[str, int], str] = {}
    resolver, fake = _resolver_for(tmp_path, monkeypatch, listed)
    listed[(REPO, 5)] = "open"
    assert resolver(_state()) is None
    assert fake.calls == []


# ---- equivalence -------------------------------------------------------------------------


def _snapshot(repository: str, number: int) -> TaskSnapshot:
    return TaskSnapshot.create(
        repository=repository,
        issue_number=number,
        created_at="2026-10-07T12:00:00Z",
        captured_at="2026-10-07T12:00:01Z",
        issue_updated_at=UPDATED,
        title=f"Task {number}",
        body="Implement a bounded task.",
        pre_implementation_revision="a" * 40,
        default_branch="main",
        source_event_id=f"task:{repository}:{number}",
    )


def _admission(snapshot: TaskSnapshot) -> str:
    return build_admission_comment(
        AdmissionReceipt.create(
            snapshot=snapshot,
            disposition="ADMITTED_PRIMARY_FRESH_TASK",
            activation_boundary="2026-10-07T11:59:59Z",
            activation_state="AUTOMATIC_CAPTURE_READY",
            exclusion_set_sha256="6" * 64,
            issue_state_at_admission="open",
            implementation_pr_numbers=(),
            tracked_parent_issue_number=None,
            tracked_parent_created_at=None,
            admitted_at="2026-10-07T12:00:02Z",
        )
    )


def _world() -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    issues: dict[str, list[dict[str, Any]]] = {REPO: [], REPO_B: []}
    comments: dict[str, list[dict[str, Any]]] = {}
    for repository, number, kind in (
        (REPO, 11, "full"),
        (REPO, 12, "no_capture"),
        (REPO, 13, "no_admission"),
        (REPO, 14, "bot"),
        (REPO_B, 21, "full"),
        (REPO_B, 22, "no_admission"),
        (REPO_B, 23, "full"),
    ):
        user = {"login": "github-actions[bot]" if kind == "bot" else "James3014"}
        issues[repository].append(
            _issue(number, state="open", user=user)  # state is recorded but not required
        )
        key = f"{repository}#{number}"
        snapshot = _snapshot(repository, number)
        rows: list[dict[str, Any]] = []
        if kind in ("full", "no_admission"):
            rows.append({"body": build_capture_comment(snapshot)})
        if kind == "full":
            rows.append({"body": _admission(snapshot)})
        rows.append({"body": "unrelated chatter"})
        comments[key] = rows if kind != "no_capture" and kind != "bot" else []
        issues[repository][-1]["comments"] = len(comments[key])
    return issues, comments


_REAL_CACHED_COMMENTS = daemon._cached_comments


def _run_ingest(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    issues: dict[str, list[dict[str, Any]]],
    comments: dict[str, list[dict[str, Any]]],
    *,
    cached: bool,
) -> tuple[dict[str, Any], int]:
    gets: list[str] = []

    def fake_comments(repository: str, number: int) -> list[dict[str, Any]]:
        gets.append(f"{repository}#{number}")
        return list(comments[f"{repository}#{number}"])

    monkeypatch.setattr(daemon, "CANDIDATE_REPOSITORIES", (REPO, REPO_B))
    monkeypatch.setattr(daemon, "_issues_since", lambda repository, since: issues[repository])
    monkeypatch.setattr(daemon, "_comments", fake_comments)
    monkeypatch.setattr(daemon, "_cached_comments", _REAL_CACHED_COMMENTS)
    if not cached:
        monkeypatch.setattr(
            daemon,
            "_cached_comments",
            lambda cache_root, repository, issue, **_: daemon._comments(
                repository, int(issue["number"])
            ),
        )
    report = daemon.ingest(store=AutomaticReplicationStore(root), since="2026-10-01T00:00:00Z")
    return report, len(gets)


def _state_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.glob("tasks/*/state.json"))
    }


def test_ingest_with_cache_is_equivalent_to_uncached_and_warm_run_makes_no_gets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues, comments = _world()
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    report_a, gets_a = _run_ingest(root_a, monkeypatch, issues, comments, cached=False)
    report_b, gets_b = _run_ingest(root_b, monkeypatch, issues, comments, cached=True)
    assert gets_a == gets_b == 7
    assert report_a["missing_capture"] == [f"{REPO}#12"]
    assert report_a["missing_admission"] == [f"{REPO}#13", f"{REPO_B}#22"]
    assert report_a["not_captured_github_token_issue"] == [f"{REPO}#14"]
    assert report_a["mirrored_count"] == 5
    assert json.dumps(report_a, sort_keys=True) == json.dumps(report_b, sort_keys=True)
    assert set(report_a) == set(report_b)
    assert _state_bytes(root_a) == _state_bytes(root_b)
    assert len(_state_bytes(root_b)) == 5
    assert (root_b / "comment-cache").is_dir()

    report_warm, gets_warm = _run_ingest(root_b, monkeypatch, issues, comments, cached=True)
    assert gets_warm == 0
    assert json.dumps(report_warm, sort_keys=True) == json.dumps(report_a, sort_keys=True)
    assert _state_bytes(root_a) == _state_bytes(root_b)


def test_ingest_records_listed_issue_states_without_changing_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues, comments = _world()
    issues[REPO][0]["state"] = "closed"
    issues[REPO][1].pop("state")
    listed: dict[tuple[str, int], str] = {}
    monkeypatch.setattr(daemon, "CANDIDATE_REPOSITORIES", (REPO, REPO_B))
    monkeypatch.setattr(daemon, "_issues_since", lambda repository, since: issues[repository])
    monkeypatch.setattr(daemon, "_comments", lambda r, n: list(comments[f"{r}#{n}"]))
    plain = daemon.ingest(
        store=AutomaticReplicationStore(tmp_path / "p"), since="2026-10-01T00:00:00Z"
    )
    with_states = daemon.ingest(
        store=AutomaticReplicationStore(tmp_path / "q"),
        since="2026-10-01T00:00:00Z",
        listed_issue_states=listed,
    )
    assert json.dumps(plain, sort_keys=True) == json.dumps(with_states, sort_keys=True)
    assert listed[(REPO, 11)] == "closed"
    assert listed[(REPO, 12)] == ""
    assert listed[(REPO, 14)] == "open"  # recorded even for the uncaptured bot issue
    assert listed[(REPO_B, 21)] == "open"
    assert len(listed) == 7


def test_ingest_with_unwritable_cache_gives_the_same_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues, comments = _world()
    report_a, _ = _run_ingest(tmp_path / "a", monkeypatch, issues, comments, cached=False)
    root_b = tmp_path / "b"
    root_b.mkdir()
    (root_b / "comment-cache").write_text("blocks the cache directory", encoding="utf-8")
    report_b, gets_b = _run_ingest(root_b, monkeypatch, issues, comments, cached=True)
    assert gets_b == 7
    assert json.dumps(report_a, sort_keys=True) == json.dumps(report_b, sort_keys=True)
    assert _state_bytes(tmp_path / "a") == _state_bytes(root_b)


def test_cache_cleanup_failure_after_write_failure_is_best_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _Fetcher(monkeypatch)

    def boom(src: Any, dst: Any) -> None:
        raise OSError("replace failed")

    def unlink_boom(self: Path, missing_ok: bool = False) -> None:
        raise OSError("unlink failed")

    monkeypatch.setattr(daemon.os, "replace", boom)
    monkeypatch.setattr(daemon.Path, "unlink", unlink_boom)
    assert daemon._cached_comments(tmp_path, REPO, _issue(), now=T0) == [{"body": "fetch-1"}]
    assert not _cache_file(tmp_path).exists()


@pytest.mark.parametrize("rows", [[None], [{"body": "ok"}, "text"], [[]]])
def test_cached_non_dict_comment_rows_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: list[Any]
) -> None:
    fetch = _Fetcher(monkeypatch)
    path = _cache_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "updated_at": UPDATED,
            "fetched_at": "2026-10-15T12:00:00Z",
            "comment_count": 1,
            "comments": rows,
        }),
        encoding="utf-8",
    )
    assert daemon._cached_comments(tmp_path, REPO, _issue(), now=T0) == [{"body": "fetch-1"}]
    assert len(fetch.calls) == 1
