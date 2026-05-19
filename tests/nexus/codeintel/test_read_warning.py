from __future__ import annotations

from pathlib import Path

from nexus.services.codeintel.read_warning import build_large_read_warning_receipt


def test_large_read_warning_is_observation_only_for_missing_skeleton_lookup(tmp_path: Path) -> None:
    source = tmp_path / "large.py"
    source.write_text("\n".join("x = 1" for _ in range(6)) + "\n", encoding="utf-8")

    receipt = build_large_read_warning_receipt(file_path=source, line_threshold=5)

    assert receipt["status"] == "WARN"
    assert receipt["warning_code"] == "large_read_without_skeleton_lookup"
    assert receipt["observation_only"] is True


def test_large_read_warning_passes_when_skeleton_lookup_found(tmp_path: Path) -> None:
    source = tmp_path / "large.py"
    source.write_text("\n".join("x = 1" for _ in range(6)) + "\n", encoding="utf-8")

    receipt = build_large_read_warning_receipt(
        file_path=source,
        skeleton_lookup_receipt={"found": True},
        line_threshold=5,
    )

    assert receipt["status"] == "PASS"
    assert receipt["warning_code"] == ""
    assert receipt["skeleton_lookup_found"] is True


def test_large_read_warning_does_not_warn_for_small_files(tmp_path: Path) -> None:
    source = tmp_path / "small.py"
    source.write_text("x = 1\n", encoding="utf-8")

    receipt = build_large_read_warning_receipt(file_path=source, line_threshold=5)

    assert receipt["status"] == "PASS"
    assert receipt["line_count"] == 1
