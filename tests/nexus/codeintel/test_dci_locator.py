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
