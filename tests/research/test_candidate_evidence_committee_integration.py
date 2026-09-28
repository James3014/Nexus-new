from __future__ import annotations

import json
from pathlib import Path

from nexus.committee.controller import CommitteeControllerV263
from nexus.verifiers.packs.astropy_pack import AstropyPack
from nexus.verifiers.packs.registry import PackRegistry


def test_generic_committee_collects_all_candidates_without_training_promotion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    evidence_root = tmp_path / "candidate-evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_RATE_PERCENT", "100")
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setenv("NEXUS_USE_PACKS", "1")

    PackRegistry.clear()
    PackRegistry.register(AstropyPack())
    controller = CommitteeControllerV263("collector-committee-task")
    receipt = controller.process_proposals([
        {
            "model": "14B",
            "attempt": 1,
            "raw_label": "r:0",
            "artifacts": ["import pandas as pd\npd.read_csv()"],
        },
        {
            "model": "7B",
            "attempt": 2,
            "raw_label": "r:0",
            "artifacts": ["xr.open_dataset()"],
        },
    ])

    collection = controller.last_candidate_evidence_collection
    assert collection["status"] == "COLLECTED"
    assert collection["collected_count"] == 2
    # Critic verdicts are useful shadow evidence but are deliberately not
    # equivalent to an isolated executable verifier.
    assert collection["eligible_count"] == 0

    group_dir = evidence_root / "groups" / collection["group_sha256"]
    rows = [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(group_dir.glob("*.json"))
    ]
    assert len(rows) == 2
    assert {row["label_quality"] for row in rows} == {"CRITIC_AGGREGATE"}
    assert all(row["dataset_eligible"] is False for row in rows)
    assert {row["candidate_id"] for row in rows} == {
        candidate.candidate_id for candidate in receipt.candidates
    }
    assert [row["candidate_id"] for row in rows if row["selected"]] == [receipt.winner_id]


def test_committee_collection_failure_cannot_change_winner(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setenv("NEXUS_USE_PACKS", "1")
    PackRegistry.clear()
    PackRegistry.register(AstropyPack())

    def _boom(**_kwargs):
        raise RuntimeError("sidecar unavailable")

    monkeypatch.setattr(
        "nexus.research.clm_system_one.candidate_evidence_collector.collect_candidate_group",
        _boom,
    )
    controller = CommitteeControllerV263("collector-failure-task")
    receipt = controller.process_proposals([
        {
            "model": "14B",
            "attempt": 1,
            "raw_label": "r:0",
            "artifacts": ["import pandas as pd\npd.read_csv()"],
        },
        {
            "model": "7B",
            "attempt": 2,
            "raw_label": "r:0",
            "artifacts": ["xr.open_dataset()"],
        },
    ])
    assert receipt.winner_id is not None
    assert controller.last_candidate_evidence_collection["status"] == "ERROR"
    assert controller.last_candidate_evidence_collection["error_type"] == "RuntimeError"
