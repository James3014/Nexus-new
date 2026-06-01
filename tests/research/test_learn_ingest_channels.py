from __future__ import annotations

from pathlib import Path

from nexus.research.learn_mode import LearnModeService


def test_ingest_preserves_required_contract_fields(tmp_path: Path) -> None:
    source_file = tmp_path / "source.md"
    source_file.write_text(
        "Nexus pipeline uses cited claims. MemPalace verifies knowledge before writeback.",
        encoding="utf-8",
    )

    service = LearnModeService(tmp_path)
    payload = service.ingest(source="repo:nexus", source_file=str(source_file), topic="nexus")

    for key in (
        "status",
        "claims_count",
        "verified_claims_count",
        "sources_count",
        "documents_ingested",
        "channel_counts",
    ):
        assert key in payload
    assert payload["claims_count"] >= 1
    assert "tactical_data" in payload["channel_counts"]
    assert "governance_principles" in payload["channel_counts"]


def test_ingest_source_file_override_avoids_repo_source_path_error(tmp_path: Path) -> None:
    source_file = tmp_path / "manual_source.md"
    source_file.write_text(
        "Repo Scout discovers repository structure and emits cited summaries.",
        encoding="utf-8",
    )

    service = LearnModeService(tmp_path)
    payload = service.ingest(source="repo:repo-scout", source_file=str(source_file), topic="repo-scout")
    assert payload["status"] == "SUCCESS"


def test_ingest_accepts_multiple_sources(tmp_path: Path) -> None:
    service = LearnModeService(tmp_path)
    payload = service.ingest(source=["alpha-keyword", "beta-keyword"], topic="nexus")
    assert payload["status"] == "SUCCESS"
    assert payload["documents_ingested"] >= 2
    assert payload["sources_count"] >= 2


def test_ingest_rejects_source_file_with_multiple_sources(tmp_path: Path) -> None:
    source_file = tmp_path / "source.md"
    source_file.write_text("single source file", encoding="utf-8")
    service = LearnModeService(tmp_path)
    try:
        service.ingest(source=["a", "b"], source_file=str(source_file), topic="nexus")
    except ValueError as exc:
        assert "source_file requires exactly one source" in str(exc)
    else:
        assert False, "expected ValueError when source_file is combined with multiple sources"


def test_ingest_rejects_empty_source_list(tmp_path: Path) -> None:
    service = LearnModeService(tmp_path)
    try:
        service.ingest(source=[], topic="nexus")
    except ValueError as exc:
        assert "source must be non-empty" in str(exc)
    else:
        assert False, "expected ValueError for empty source list"
