from __future__ import annotations

import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "ops" / "fast_start_v2_github.py"
SPEC = importlib.util.spec_from_file_location("fast_start_v2_github", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
gh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gh)


class _Response:
    def __init__(self, payload: object) -> None:
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.raw


def _http_error(
    *,
    code: int = 403,
    body: str,
    headers: dict[str, str] | None = None,
) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.github.com/repos/James3014/Nexus-new/issues/549",
        code,
        "Forbidden",
        headers or {},
        io.BytesIO(body.encode("utf-8")),
    )


def test_get_rate_limit_retries_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(_request, timeout):
        nonlocal calls
        assert timeout == 20
        calls += 1
        if calls == 1:
            raise _http_error(
                body='{"message":"API rate limit exceeded for installation"}',
                headers={"X-RateLimit-Remaining": "0", "Retry-After": "0"},
            )
        return _Response({"number": 549})

    monkeypatch.setattr(gh.urllib.request, "urlopen", fake_urlopen)
    client = gh.GitHubMetadataClient(
        "token",
        repository="James3014/Nexus-new",
        sleep=sleeps.append,
    )

    result = client.request("/repos/James3014/Nexus-new/issues/549")

    assert result == {"number": 549}
    assert calls == 2
    assert sleeps == [0.0]


def test_get_rate_limit_exhaustion_is_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    def fake_urlopen(_request, timeout):
        raise _http_error(
            body='{"message":"API rate limit exceeded for installation"}',
            headers={"X-RateLimit-Remaining": "0", "Retry-After": "120"},
        )

    monkeypatch.setattr(gh.urllib.request, "urlopen", fake_urlopen)
    client = gh.GitHubMetadataClient(
        "token",
        repository="James3014/Nexus-new",
        sleep=sleeps.append,
    )

    with pytest.raises(gh.GitHubRateLimitExhausted) as raised:
        client.request("/repos/James3014/Nexus-new/issues/549")

    assert raised.value.retry_after == 120.0
    assert sleeps == []


def test_permission_403_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    def fake_urlopen(_request, timeout):
        raise _http_error(
            body='{"message":"Resource not accessible by integration"}',
            headers={"X-RateLimit-Remaining": "4999"},
        )

    monkeypatch.setattr(gh.urllib.request, "urlopen", fake_urlopen)
    client = gh.GitHubMetadataClient(
        "token",
        repository="James3014/Nexus-new",
        sleep=sleeps.append,
    )

    with pytest.raises(gh.GitHubTransportError, match="GITHUB_GET_FAILED:HTTP_403"):
        client.request("/repos/James3014/Nexus-new/issues/549")

    assert sleeps == []


def test_patch_rate_limit_is_never_blindly_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        raise _http_error(
            body='{"message":"API rate limit exceeded for installation"}',
            headers={"X-RateLimit-Remaining": "0", "Retry-After": "0"},
        )

    monkeypatch.setattr(gh.urllib.request, "urlopen", fake_urlopen)
    client = gh.GitHubMetadataClient(
        "token",
        repository="James3014/Nexus-new",
        sleep=sleeps.append,
    )

    with pytest.raises(gh.GitHubTransportError, match="GITHUB_WRITE_RATE_LIMITED"):
        client.request(
            "/repos/James3014/Nexus-new/issues/549",
            method="PATCH",
            payload={"body": "new"},
        )

    assert calls == 1
    assert sleeps == []


def test_patch_transport_loss_is_outcome_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(_request, timeout):
        raise urllib.error.URLError("lost ack")

    monkeypatch.setattr(gh.urllib.request, "urlopen", fake_urlopen)
    client = gh.GitHubMetadataClient("token", repository="James3014/Nexus-new")

    with pytest.raises(gh.GitHubWriteOutcomeUnknown, match="GITHUB_WRITE_OUTCOME_UNKNOWN"):
        client.request(
            "/repos/James3014/Nexus-new/issues/549",
            method="PATCH",
            payload={"body": "new"},
        )


def test_rate_limit_reset_header_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _http_error(
                body='{"message":"API rate limit exceeded for installation"}',
                headers={
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": "1002",
                },
            )
        return _Response({"ok": True})

    monkeypatch.setattr(gh.urllib.request, "urlopen", fake_urlopen)
    client = gh.GitHubMetadataClient(
        "token",
        repository="James3014/Nexus-new",
        sleep=sleeps.append,
        clock=lambda: 1000.0,
    )

    assert client.request("/repos/James3014/Nexus-new/issues/549") == {"ok": True}
    assert sleeps == [3.0]


def test_collect_pr_changed_paths_is_bounded_and_sorted() -> None:
    class Client:
        def request(self, path: str):
            assert path.endswith("page=1")
            return [
                {"filename": "z.py"},
                {"filename": "a.py"},
                {"filename": "z.py"},
            ]

    assert gh.collect_pr_changed_paths(
        Client(),
        repository="James3014/Nexus-new",
        pr_number=1509,
    ) == ["a.py", "z.py"]


def test_changed_paths_cli_rate_limit_writes_unavailable_witness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, path: str):
            raise gh.GitHubRateLimitExhausted(
                method="GET",
                path=path,
                retry_after=395.0,
            )

    monkeypatch.setattr(gh, "GitHubMetadataClient", Client)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    output = tmp_path / "paths.txt"

    args = type(
        "Args",
        (),
        {
            "repository": "James3014/Nexus-new",
            "pr_number": 1509,
            "output": str(output),
        },
    )()
    code = gh._cli_changed_paths(args)

    assert code == gh.RATE_LIMIT_EXIT
    assert output.read_text(encoding="utf-8") == ""
    witness = json.loads(capsys.readouterr().out)
    assert witness["status"] == "UNAVAILABLE"
    assert witness["authority"] == "ADVISORY_CACHE_ONLY"
    assert witness["reason"] == "GITHUB_RATE_LIMIT_EXHAUSTED"

def test_collect_compare_changed_paths_validates_and_sorts() -> None:
    before = "1" * 40
    after = "2" * 40

    class Client:
        def request(self, path: str):
            assert path.endswith(f"/compare/{before}...{after}")
            return {
                "files": [
                    {"filename": "z.py"},
                    {"filename": "a.py"},
                    {"filename": "z.py"},
                ]
            }

    assert gh.collect_compare_changed_paths(
        Client(),
        repository="James3014/Nexus-new",
        before_sha=before,
        after_sha=after,
    ) == ["a.py", "z.py"]


def test_compare_changed_paths_rejects_malformed_sha() -> None:
    class Client:
        def request(self, path: str):
            raise AssertionError("network must not be reached")

    with pytest.raises(ValueError, match="BEFORE_SHA_INVALID"):
        gh.collect_compare_changed_paths(
            Client(),
            repository="James3014/Nexus-new",
            before_sha="bad",
            after_sha="2" * 40,
        )

def test_committed_fast_start_workflow_uses_bounded_github_transport() -> None:
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "fast-start-v2-invalidator.yml"
    ).read_text(encoding="utf-8")

    assert "scripts/ops/fast_start_v2_github.py changed-paths" in workflow
    assert "scripts/ops/fast_start_v2_github.py compare-paths" in workflow
    assert "steps.paths.outputs.unavailable == 'true'" in workflow
    assert "from scripts.ops.fast_start_v2_github import (" in workflow
    assert "FAST_START_POST_WRITE_READBACK_RATE_LIMIT_EXHAUSTED" in workflow
    assert "GitHubMetadataClient(TOKEN, repository=REPOSITORY)" in workflow
