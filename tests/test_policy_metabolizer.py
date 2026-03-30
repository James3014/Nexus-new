import json
from datetime import datetime, timedelta, timezone

from nexus.core.policy_metabolizer import PolicyMetabolizer


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_policy_metabolizer_archives_high_decay_records(tmp_path):
    policy_path = tmp_path / ".nexus" / "knowledge" / "policy_memory.jsonl"
    old_time = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    rows = [
        {
            "rule_id": "POL-OLD",
            "confidence": 0.1,
            "created_at": old_time,
            "semantic_drift": 90.0,
            "zero_decay": False,
        },
        {
            "rule_id": "POL-KEEP",
            "confidence": 0.9,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "semantic_drift": 0.0,
            "zero_decay": False,
        },
    ]
    _write_jsonl(policy_path, rows)

    result = PolicyMetabolizer(str(tmp_path)).metabolize(force=True)

    assert result.scanned == 2
    assert result.archived == 1
    assert result.active == 1
    assert result.snapshot_path is not None
    assert result.archive_path.exists()
    with open(policy_path, "r", encoding="utf-8") as handle:
        kept = [json.loads(line) for line in handle if line.strip()]
    assert len(kept) == 1
    assert kept[0]["rule_id"] == "POL-KEEP"


def test_policy_metabolizer_respects_zero_decay(tmp_path):
    policy_path = tmp_path / ".nexus" / "knowledge" / "policy_memory.jsonl"
    old_time = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    rows = [
        {
            "rule_id": "POL-SIR",
            "confidence": 0.0,
            "created_at": old_time,
            "semantic_drift": 100.0,
            "zero_decay": True,
            "tags": ["sir_directive"],
        }
    ]
    _write_jsonl(policy_path, rows)

    result = PolicyMetabolizer(str(tmp_path)).metabolize(force=True)
    assert result.archived == 0
    with open(policy_path, "r", encoding="utf-8") as handle:
        kept = [json.loads(line) for line in handle if line.strip()]
    assert kept[0]["rule_id"] == "POL-SIR"
