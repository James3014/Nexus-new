from __future__ import annotations

import json
from pathlib import Path

from nexus.services.codeintel.dci_locator import locate_dci_evidence, should_enable_dci


def test_dci_locator_writes_scoped_evidence_report(tmp_path: Path):
    target = tmp_path / "nexus" / "parser.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "def canonical_parser(value):\n"
        "    return value.strip()\n",
        encoding="utf-8",
    )
    report_path = tmp_path / ".nexus" / "reports" / "codeintel" / "dci.json"

    report = locate_dci_evidence(
        tmp_path,
        task_desc="Synchronize canonical parser evidence.",
        target_file=str(target),
        report_path=report_path,
        route_lane="context_sync_capped",
    )

    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "nexus_dci_evidence_locator.v1"
    assert report["invoked"] is True
    assert report["evidence_refs"]
    assert report["localized_spans"][0]["file"] == "nexus/parser.py"
    assert saved["evidence_refs"] == report["evidence_refs"]


def test_dci_admission_skips_lite_hidden_lane():
    assert should_enable_dci(route_lane="hidden_lite", codeintel_empty=True) is False
    assert should_enable_dci(route_lane="context_sync_capped") is True


def _files_in_span_order(report) -> list[str]:
    out: list[str] = []
    for span in report["localized_spans"]:
        if span["file"] not in out:
            out.append(span["file"])
    return out


def test_dci_locator_ranks_by_relevance_not_folder_walk_order(tmp_path: Path):
    # Files that sort first in the walk mention a query word many times but are not about the task.
    for index in range(40):
        (tmp_path / "aaa").mkdir(exist_ok=True)
        (tmp_path / "aaa" / f"noise_{index:02d}.py").write_text("x = 'retry'\n" * 20, encoding="utf-8")
    target = tmp_path / "zzz" / "lancedb_fallback.py"
    target.parent.mkdir()
    target.write_text(
        "def lancedb_fallback_search(query):\n    # lancedb fallback substring search\n    return []\n",
        encoding="utf-8",
    )
    report = locate_dci_evidence(
        tmp_path,
        task_desc="LanceDB fallback search never matches: lancedb_fallback_search retry",
        target_file="",
        report_path=tmp_path / "out" / "dci.json",
    )
    assert _files_in_span_order(report)[0] == "zzz/lancedb_fallback.py"
    assert report["ranked_files"][0]["file"] == "zzz/lancedb_fallback.py"
    assert report["ranking"] == "bm25_path_symbol_impact"


def test_dci_locator_spreads_span_budget_across_ranked_files(tmp_path: Path):
    for name in ("alpha", "beta", "gamma"):
        (tmp_path / f"{name}_parser.py").write_text("parser canonical\n" * 30, encoding="utf-8")
    report = locate_dci_evidence(
        tmp_path,
        task_desc="canonical parser",
        target_file="",
        report_path=tmp_path / "out" / "dci.json",
        max_matches=3,
    )
    assert len(report["localized_spans"]) == 3
    assert len(_files_in_span_order(report)) == 3


def test_dci_locator_target_file_stays_first_and_state_dir_is_skipped(tmp_path: Path):
    (tmp_path / ".nexus" / "reports").mkdir(parents=True)
    (tmp_path / ".nexus" / "reports" / "old.json").write_text('{"canonical parser": 1}', encoding="utf-8")
    (tmp_path / "other.py").write_text("canonical parser canonical parser\n", encoding="utf-8")
    target = tmp_path / "pkg" / "unrelated.py"
    target.parent.mkdir()
    target.write_text("value = 1\n", encoding="utf-8")
    report = locate_dci_evidence(
        tmp_path,
        task_desc="canonical parser",
        target_file="pkg/unrelated.py",
        report_path=tmp_path / ".nexus" / "reports" / "dci.json",
    )
    files = _files_in_span_order(report)
    assert files[0] == "pkg/unrelated.py"
    assert "other.py" in files
    assert not any(item["file"].startswith(".nexus/") for item in report["ranked_files"])
    assert report["ranked_files"][0]["score"] is None
    json.loads(Path(report["report_path"]).read_text(encoding="utf-8"))  # strict JSON, no Infinity
