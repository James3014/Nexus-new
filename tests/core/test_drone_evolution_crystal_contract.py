import json

from nexus.core.drone_engine import TacticalDrone


def test_save_evolution_crystal_includes_semantic_contract_fields(tmp_path):
    drone = TacticalDrone(drone_id="d1", project_root=tmp_path)
    drone.status = "SUCCESS"
    out = tmp_path / ".nexus" / "reports" / "drones" / "d1_crystal.json"
    drone.save_evolution_crystal(out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["drone_id"] == "d1"
    assert payload["semantic_status"] == "VERIFIED"
    assert payload["runtime_classification"] == "verified_pass"
    assert payload["artifact_path"] == str(out)
