from __future__ import annotations

import json

from click.testing import CliRunner

from scripts.engine.nexus_cli import nexus


def test_local_assist_interface_cli_emits_machine_readable_json(tmp_path) -> None:
    task = tmp_path / "task.json"
    task.write_text(
        json.dumps(
            {
                "task_id": "m6-a-cli-001",
                "workspace_revision": "rev-1",
                "task_statement": "implement a bounded bug fix in one file",
                "task_type": "bugfix",
                "route": {"route_features": {"risk_score": 20, "adjusted_root_cause_confidence": 0.9}},
                "allowed_files": ["target.py"],
                "target_file": "target.py",
            }
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        nexus,
        ["local-assist", "interface", "--task-file", str(task), "--workspace", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "nexus.local_assist.agent_interface.v1"
    assert payload["task_identity"]["task_id"] == "m6-a-cli-001"
    assert payload["provider_neutral"] is True


def test_canonical_run_exposes_backward_compatible_policy_switch() -> None:
    result = CliRunner().invoke(nexus, ["run", "--help"])
    assert result.exit_code == 0
    assert "--local-assist-policy" in result.output
    assert "planner" in result.output
    assert "explicit" in result.output
    assert "disabled" in result.output
