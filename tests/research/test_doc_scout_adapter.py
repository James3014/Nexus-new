from pathlib import Path

from nexus.research.doc_scout_adapter import DocScoutAdapter


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
