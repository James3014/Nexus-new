from __future__ import annotations

import io
import json
import urllib.error

import pytest

from scripts.ops.github_read_retry import (
    GitHubReadError,
    GitHubReadRateLimitExhausted,
    github_json_get,
)


class FakeResponse:
    def __init__(self, payload: object):
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit: int) -> bytes:
        return self.raw


def http_error(
    *,
    body: str,
    headers: dict[str, str] | None = None,
    code: int = 403,
) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.github.com/repos/owner/repo",
        code,
        "Forbidden",
        headers or {},
        io.BytesIO(body.encode("utf-8")),
    )


def test_rate_limit_retry_reuses_same_get_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    sleeps: list[float] = []

    def fake_urlopen(request, timeout):
        assert timeout == 20.0
        calls.append((request.full_url, request.get_method()))
        if len(calls) == 1:
            raise http_error(
                body='{"message":"API rate limit exceeded for installation"}',
                headers={"X-RateLimit-Remaining": "0", "Retry-After": "0"},
            )
        return FakeResponse({"ok": True})

    monkeypatch.setattr("scripts.ops.github_read_retry.urllib.request.urlopen", fake_urlopen)

    payload = github_json_get(
        "/repos/owner/repo",
        token="token",
        sleep_fn=sleeps.append,
        clock_fn=lambda: 1000.0,
    )

    assert payload == {"ok": True}
    assert calls == [
        ("https://api.github.com/repos/owner/repo", "GET"),
        ("https://api.github.com/repos/owner/repo", "GET"),
    ]
    assert sleeps == [0.0]


def test_rate_limit_retry_honors_reset_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(_request, timeout):
        nonlocal calls
        assert timeout == 20.0
        calls += 1
        if calls == 1:
            raise http_error(
                body='{"message":"API rate limit exceeded for installation"}',
                headers={
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": "1002",
                },
            )
        return FakeResponse({"ok": True})

    monkeypatch.setattr("scripts.ops.github_read_retry.urllib.request.urlopen", fake_urlopen)

    assert (
        github_json_get(
            "/repos/owner/repo",
            token="token",
            max_wait_seconds=5.0,
            sleep_fn=sleeps.append,
            clock_fn=lambda: 1000.0,
        )
        == {"ok": True}
    )
    assert sleeps == [3.0]


def test_rate_limit_exhaustion_is_distinct_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    def fake_urlopen(_request, timeout):
        assert timeout == 20.0
        raise http_error(
            body='{"message":"API rate limit exceeded for installation"}',
            headers={"X-RateLimit-Remaining": "0", "Retry-After": "120"},
        )

    monkeypatch.setattr("scripts.ops.github_read_retry.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(
        GitHubReadRateLimitExhausted,
        match=r"GITHUB_READ_RATE_LIMIT_EXHAUSTED: .*retry_after_seconds=120\.000",
    ):
        github_json_get(
            "/repos/owner/repo",
            token="token",
            max_wait_seconds=60.0,
            sleep_fn=sleeps.append,
        )

    assert sleeps == []


def test_ordinary_permission_403_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == 20.0
        raise http_error(
            body='{"message":"Resource not accessible by integration"}',
            headers={"X-RateLimit-Remaining": "4999"},
        )

    monkeypatch.setattr("scripts.ops.github_read_retry.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(GitHubReadError, match=r"GitHub GET failed: HTTP 403"):
        github_json_get(
            "/repos/owner/repo",
            token="token",
            sleep_fn=sleeps.append,
        )

    assert calls == 1
    assert sleeps == []


def test_non_rate_limit_http_error_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(_request, timeout):
        assert timeout == 20.0
        raise http_error(
            body='{"message":"Not Found"}',
            code=404,
        )

    monkeypatch.setattr("scripts.ops.github_read_retry.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(GitHubReadError, match=r"HTTP 404"):
        github_json_get("/repos/owner/missing", token="token")
