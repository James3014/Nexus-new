from __future__ import annotations

import json

from scripts.engine.commands.research_support import read_json_file, research_preflight_block_payload


def test_read_json_file_resolves_relative_paths(tmp_path):
    payload_path = tmp_path / "reports" / "route.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")

    assert read_json_file(tmp_path, "reports/route.json") == {"status": "PASS"}
    assert read_json_file(tmp_path, None) == {}


def test_research_preflight_block_payload_preserves_completion_contract():
    payload = research_preflight_block_payload(
        command_name="research:auto-flow",
        task_name="verify sdk contract",
        preflight={
            "blocked": True,
            "block_reasons": ["claim_uncertainty_requires_research"],
            "next_action": "verify_contract_before_editing",
        },
    )

    assert payload["status"] == "blocked"
    assert payload["semantic_status"] == "BLOCKED"
    assert payload["blocker_type"] == "research_preflight"
    assert payload["execution_path"] == "cli->research:auto-flow->research_session_preflight"
    assert payload["next_action"] == "verify_contract_before_editing"
