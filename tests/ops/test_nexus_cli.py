import json

import pytest
from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_module
from nexus.core.exit_codes import NexusExitCode


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


@pytest.mark.parametrize(
    ("promoted", "expected_exit", "expected_status"),
    [
        (True, NexusExitCode.SUCCESS, "SUCCESS"),
        (False, NexusExitCode.FAILED, "FAILED"),
    ],
)
def test_oracle_apply_writes_bounded_report_and_uses_canonical_exit(
    monkeypatch, tmp_path, promoted, expected_exit, expected_status
) -> None:
    import nexus.oracle.promote as promote_module

    monkeypatch.setattr(cli_module, "repo_root", tmp_path)
    monkeypatch.setattr(promote_module, "promote_shadow_patch", lambda _root, _tid: promoted)

    result = CliRunner().invoke(
        cli_module.nexus,
        [
            "nexus",
            "oracle:apply",
            "shadow-1",
            "--report-file",
            "reports/oracle-apply.json",
            "--output-json",
        ],
    )

    expected_payload = {"status": expected_status, "shadow_tid": "shadow-1"}
    assert result.exit_code == expected_exit, result.output
    assert json.loads(result.output) == expected_payload
    assert json.loads((tmp_path / "reports/oracle-apply.json").read_text()) == expected_payload
