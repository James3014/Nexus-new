from pathlib import Path

from nexus.research.doc_scout_adapter import (
    ArxivScoutProvider,
    DocScoutAdapter,
    ExternalScoutProvider,
    FetchedExternalScoutProvider,
    GitHubIssueScoutProvider,
    SpecUrlScoutProvider,
)


class FakeIssueProvider:
    name = "fake_github_issue"

    def search(self, query: str, *, tokens: list[str], limit: int):
        return [
            {
                "path": "https://github.example/issues/42",
                "score": 3.5,
                "source": "github_issue",
                "snippet": "Known websocket timeout race fixed by cancelling stale task.",
                "source_url": "https://github.example/issues/42",
            }
        ]


def test_doc_scout_adapter_returns_hits_for_matching_docs(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "notes.md").write_text(
        "Fix websocket timeout race in coordinator path.\nClaim verification required.\n",
        encoding="utf-8",
    )

    out = DocScoutAdapter(tmp_path).search("fix websocket timeout race", limit=5)
    assert out["status"] == "SUCCESS"
    assert out["hits_count"] >= 1
    assert out["confidence"] > 0
    assert any("websocket" in str(item.get("snippet", "")).lower() for item in out["hits"])


def test_doc_scout_adapter_handles_empty_query(tmp_path: Path):
    out = DocScoutAdapter(tmp_path).search("", limit=3)
    assert out["status"] == "EMPTY_QUERY"
    assert out["hits_count"] == 0
    assert out["external_metadata"]["source_count"] == 0
    assert out["external_metadata"]["error_count"] == 0
    assert out["external_metadata"]["latency_ms"] == 0.0
    assert out["external_metadata"]["cache_age_sec"] == 0.0


def test_doc_scout_adapter_supports_external_provider_with_traceable_source(tmp_path: Path):
    out = DocScoutAdapter(tmp_path, external_providers=[FakeIssueProvider()]).search(
        "websocket timeout race",
        limit=3,
        include_external=True,
    )

    assert out["status"] == "SUCCESS"
    assert out["external_enabled"] is True
    assert out["hits"][0]["source"] == "github_issue"
    assert out["hits"][0]["source_url"] == "https://github.example/issues/42"


def test_doc_scout_external_provider_rejects_unverified_sources_and_caches(tmp_path: Path):
    provider = GitHubIssueScoutProvider(
        [
            {
                "source_url": "https://github.example/issues/42",
                "snippet": "Known websocket timeout race fixed by cancelling stale task.",
            },
            {
                "source_url": "file:///tmp/local.txt",
                "snippet": "This local path is not external claim evidence.",
            },
        ]
    )
    adapter = DocScoutAdapter(tmp_path, external_providers=[provider])

    first = adapter.search("websocket timeout race", limit=3, include_external=True)
    second = adapter.search("websocket timeout race", limit=3, include_external=True)

    assert [hit["source_url"] for hit in first["hits"]] == ["https://github.example/issues/42"]
    assert second["hits"] == first["hits"]
    assert first["external_metadata"]["cache_status"] == "miss"
    assert first["external_metadata"]["source_count"] == 1
    assert first["external_metadata"]["error_count"] == 0
    assert first["external_metadata"]["latency_ms"] >= 0
    assert second["external_metadata"]["cache_status"] == "hit"
    assert second["external_metadata"]["cache_age_sec"] >= 0
    assert second["external_metadata"]["providers_used"] == ["github_issue"]
    assert second["external_metadata"]["verified_source_count"] == 1
    assert list((tmp_path / ".nexus" / "cache" / "doc_scout").glob("*.json"))


def test_doc_scout_has_named_opt_in_external_provider_types(tmp_path: Path):
    providers = [
        GitHubIssueScoutProvider([{"source_url": "https://github.example/issues/1", "snippet": "timeout issue"}]),
        ArxivScoutProvider([{"source_url": "https://arxiv.org/abs/1234.5678", "snippet": "timeout verification"}]),
        SpecUrlScoutProvider([{"source_url": "https://spec.example/sdk", "snippet": "SDK timeout parameter"}]),
    ]

    out = DocScoutAdapter(tmp_path, external_providers=providers).search("timeout sdk", limit=5, include_external=True)

    assert {hit["source"] for hit in out["hits"]} == {"github_issue", "arxiv", "spec"}


def test_doc_scout_fetched_provider_is_opt_in_and_uses_injected_fetcher(tmp_path: Path):
    calls = []

    def fake_fetch(url: str, *, timeout_sec: float):
        calls.append((url, timeout_sec))
        return "The upstream SDK fixed timeout cancellation race in version 2."

    provider = FetchedExternalScoutProvider(
        name="spec_fetch",
        source="spec",
        urls=["https://spec.example/sdk", "file:///tmp/not-allowed"],
        fetcher=fake_fetch,
        timeout_sec=1.5,
    )

    disabled = DocScoutAdapter(tmp_path, external_providers=[provider]).search("sdk timeout race", include_external=False)
    enabled = DocScoutAdapter(tmp_path, external_providers=[provider], cache_ttl_sec=0).search(
        "sdk timeout race",
        include_external=True,
    )

    assert disabled["external_enabled"] is False
    assert calls == [("https://spec.example/sdk", 1.5)]
    assert enabled["hits"][0]["source_url"] == "https://spec.example/sdk"
    assert enabled["external_metadata"]["providers_used"] == ["spec_fetch"]
    assert enabled["external_metadata"]["cache_status"] == "disabled"
    assert enabled["external_metadata"]["verified_source_count"] == 1
    assert enabled["external_metadata"]["source_count"] == 1


def test_doc_scout_external_provider_failure_is_measured_not_silent(tmp_path: Path):
    class BrokenProvider:
        name = "broken_spec"

        def search(self, query: str, *, tokens: list[str], limit: int):
            raise TimeoutError("boom")

    out = DocScoutAdapter(tmp_path, external_providers=[BrokenProvider()], cache_ttl_sec=0).search(
        "sdk timeout race",
        include_external=True,
    )

    assert out["external_enabled"] is True
    assert out["external_metadata"]["provider_errors"] == ["broken_spec:TimeoutError"]
    assert out["external_metadata"]["verified_source_count"] == 0
    assert out["external_metadata"]["source_count"] == 0
    assert out["external_metadata"]["error_count"] == 1
    assert out["external_metadata"]["latency_ms"] >= 0
