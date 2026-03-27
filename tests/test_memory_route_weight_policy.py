import json

from nexus.services.memory import MemoryService


def test_sync_route_phase_weights_writes_policy_entries(tmp_path):
    svc = MemoryService(str(tmp_path))
    svc.sync_route_phase_weights({"R": 20.0, "A": -10.0}, cycle_status="repaired", fault_hash="abc")

    path = tmp_path / ".nexus" / "knowledge" / "policy_memory.jsonl"
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = {row["rule_id"] for row in rows}
    assert "ROUTE-WEIGHT-R" in ids
    assert "ROUTE-WEIGHT-A" in ids
    r_row = next(row for row in rows if row["rule_id"] == "ROUTE-WEIGHT-R")
    assert r_row["source"] == "self_heal_route_weight"
    assert r_row["metadata"]["cycle_status"] == "repaired"
    assert r_row["metadata"]["fault_hash"] == "abc"


def test_sync_route_phase_weights_replaces_existing_route_weight_entries(tmp_path):
    svc = MemoryService(str(tmp_path))
    path = tmp_path / ".nexus" / "knowledge" / "policy_memory.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    seed = [
        {
            "rule_id": "ROUTE-WEIGHT-R",
            "condition": "old",
            "action": "old",
            "confidence": 0.1,
            "source": "self_heal_route_weight",
        },
        {
            "rule_id": "POL-KEEP",
            "condition": "keep",
            "action": "keep",
            "confidence": 0.9,
        },
    ]
    with open(path, "w", encoding="utf-8") as handle:
        for row in seed:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    svc.sync_route_phase_weights({"R": 60.0}, cycle_status="healthy")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["rule_id"] for row in rows]
    assert ids.count("ROUTE-WEIGHT-R") == 1
    assert "POL-KEEP" in ids
    new_row = next(row for row in rows if row["rule_id"] == "ROUTE-WEIGHT-R")
    assert new_row["metadata"]["route_weight"] == 60.0
