import json

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_module


def test_workforce_status_is_compact_read_only_and_policy_bound() -> None:
    result = CliRunner().invoke(cli_module.nexus, ["workforce", "status"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "nexus.workforce_compact_surface.v1"
    assert payload["status"] == "PASS"
    assert payload["route_authority"] == "CapabilityPlanner"
    assert len(payload["policy"]["hash"]) == 64
    assert payload["mutation_authority"] == {
        "query_only": True,
        "can_select_worker": False,
        "can_mutate_workspace": False,
        "can_approve_or_integrate": False,
    }
    assert payload["summary"]["eligible"] > 0
    assert all("worker_id" in row and "eligible" in row and "reason" in row for row in payload["workers"])


def test_workforce_status_fails_closed_when_policy_load_fails(monkeypatch) -> None:
    class BrokenLoader:
        def load(self):
            raise RuntimeError("policy drift")

    import nexus.services.model_workforce_policy as policy_module

    monkeypatch.setattr(policy_module, "WorkforcePolicyLoader", BrokenLoader)
    result = CliRunner().invoke(cli_module.nexus, ["workforce", "status"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "BLOCK"
    assert "policy_load_failed" in payload["error"]
