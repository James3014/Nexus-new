from pathlib import Path

from nexus.research.doc_scout_adapter import ArxivScoutProvider, DocScoutAdapter, ExternalScoutProvider, GitHubIssueScoutProvider, SpecUrlScoutProvider


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
    assert list((tmp_path / ".nexus" / "cache" / "doc_scout").glob("*.json"))


def test_doc_scout_has_named_opt_in_external_provider_types(tmp_path: Path):
    providers = [
        GitHubIssueScoutProvider([{"source_url": "https://github.example/issues/1", "snippet": "timeout issue"}]),
        ArxivScoutProvider([{"source_url": "https://arxiv.org/abs/1234.5678", "snippet": "timeout verification"}]),
        SpecUrlScoutProvider([{"source_url": "https://spec.example/sdk", "snippet": "SDK timeout parameter"}]),
    ]

    out = DocScoutAdapter(tmp_path, external_providers=providers).search("timeout sdk", limit=5, include_external=True)

    assert {hit["source"] for hit in out["hits"]} == {"github_issue", "arxiv", "spec"}
