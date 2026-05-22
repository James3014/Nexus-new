from __future__ import annotations

from pathlib import Path

from nexus.services.codeintel.fault_tolerant_ast_snapshot import FaultTolerantASTSnapshot


def test_fault_tolerant_ast_snapshot_uses_last_known_good_without_source_text(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("def target(value):\n    return value\n", encoding="utf-8")
    snapshot = FaultTolerantASTSnapshot(tmp_path)

    clean = snapshot.lookup("target")
    compact = snapshot.export_compact_snapshot()
    target.write_text("def target(value):\n    return value +\n", encoding="utf-8")
    restored = FaultTolerantASTSnapshot(tmp_path)
    restored.load_compact_snapshot(compact)
    fallback = restored.lookup("target")

    assert clean.found is True
    assert compact["stores_source_text"] is False
    assert "return value" not in str(compact)
    assert fallback.found is True
    assert restored.last_receipt is not None
    assert restored.last_receipt["used_last_known_good"] is True
    assert restored.last_receipt["stores_source_text"] is False
    assert restored.last_receipt["runtime_update_allowed"] is False


def test_fault_tolerant_ast_snapshot_returns_unparsable_hotspot_when_missing(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    snapshot = FaultTolerantASTSnapshot(tmp_path)

    result = snapshot.lookup("missing")

    assert result.found is False
    assert snapshot.last_receipt is not None
    assert snapshot.last_receipt["status"] == "RETURN"
    assert snapshot.last_receipt["blockers"] == ["UNPARSABLE_HOTSPOT"]
