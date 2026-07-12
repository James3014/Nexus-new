from __future__ import annotations

import json
from pathlib import Path

from nexus.services.local_assist_user_relay import validate_user_relay, write_user_relay_report


def _receipt(path: Path, task_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "nexus.local_assist.execution_receipt.v1",
                "task_id": task_id,
                "provider": "ollama",
                "resolved_model": "qwen2.5-coder:7b-instruct",
                "provider_call_count": 1,
                "receipt_complete": True,
                "claim_boundary": {"runtime_invoked": True, "output_delivered": True},
            }
        ),
        encoding="utf-8",
    )


def _package(root: Path, advisor: Path, verified: Path) -> Path:
    package = root / "package.json"
    package.write_text(
        json.dumps(
            {
                "schema": "nexus.local_assist.user_relay_package.v1",
                "status": "USER_RELAY_REQUIRED",
                "task_id": "relay-001",
                "external_delivery_mode": "human_relay",
                "delivery_authority": "user",
                "automated_exfiltration": False,
                "local_assist_receipt_present": True,
                "local_assist_receipt_refs": [advisor.name, verified.name],
                "allowed_modified_files": ["tests/example.py"],
                "verifier_required": True,
            }
        ),
        encoding="utf-8",
    )
    return package


def test_missing_user_response_stays_user_relay_required(tmp_path: Path) -> None:
    advisor = tmp_path / "advisor.json"
    verified = tmp_path / "verified.json"
    _receipt(advisor, "relay-advisor")
    _receipt(verified, "relay-verified")
    package = _package(tmp_path, advisor, verified)

    result = validate_user_relay(package_file=package, repo_root=tmp_path)

    assert result["status"] == "USER_RELAY_REQUIRED"
    assert result["automated_exfiltration"] is False
    assert result["agent_output_imported"] is False
    assert result["agent_consumed_proven"] is False


def test_valid_import_requires_both_receipt_identities_and_verifier(tmp_path: Path) -> None:
    advisor = tmp_path / "advisor.json"
    verified = tmp_path / "verified.json"
    _receipt(advisor, "relay-advisor")
    _receipt(verified, "relay-verified")
    package = _package(tmp_path, advisor, verified)
    response = tmp_path / "response.json"
    response.write_text(
        json.dumps(
            {
                "schema": "nexus.local_assist.user_relay_response.v1",
                "status": "IMPORTED",
                "external_delivery_mode": "human_relay",
                "delivery_authority": "user",
                "automated_exfiltration": False,
                "agent_output_imported": True,
                "modified_files": ["tests/example.py"],
                "verifier_result": "pass",
                "agent_consumption_evidence": [
                    "Used relay-advisor and relay-verified receipts for selection."
                ],
                "final_output": "relay-advisor relay-verified",
            }
        ),
        encoding="utf-8",
    )

    result = validate_user_relay(
        package_file=package,
        response_file=response,
        repo_root=tmp_path,
    )

    assert result["status"] == "AGENT_OPERATED_LOCAL_ASSIST_PROVEN_WITH_USER_RELAY"
    assert result["agent_output_imported"] is True
    assert result["agent_consumed_proven"] is True
    assert result["claim_boundary"]["outcome_contributed"] is False


def test_import_rejects_missing_receipt_reference(tmp_path: Path) -> None:
    advisor = tmp_path / "advisor.json"
    verified = tmp_path / "verified.json"
    _receipt(advisor, "relay-advisor")
    _receipt(verified, "relay-verified")
    package = _package(tmp_path, advisor, verified)
    response = tmp_path / "response.json"
    response.write_text(
        json.dumps(
            {
                "schema": "nexus.local_assist.user_relay_response.v1",
                "status": "IMPORTED",
                "external_delivery_mode": "human_relay",
                "delivery_authority": "user",
                "automated_exfiltration": False,
                "agent_output_imported": True,
                "modified_files": [],
                "verifier_result": "not_run",
                "agent_consumption_evidence": ["Used relay-advisor only."],
                "final_output": "relay-advisor",
            }
        ),
        encoding="utf-8",
    )

    result = validate_user_relay(
        package_file=package,
        response_file=response,
        repo_root=tmp_path,
    )

    assert result["status"] == "REJECTED"
    assert "missing_receipt_reference:relay-verified" in result["blockers"]


def test_missing_user_response_writes_machine_report(tmp_path: Path) -> None:
    advisor = tmp_path / "advisor.json"
    verified = tmp_path / "verified.json"
    _receipt(advisor, "relay-advisor")
    _receipt(verified, "relay-verified")
    package = _package(tmp_path, advisor, verified)
    report_file = tmp_path / "relay-report.json"

    report = write_user_relay_report(
        package_file=package,
        repo_root=tmp_path,
        response_file=None,
        report_file=report_file,
    )

    assert report["status"] == "USER_RELAY_REQUIRED"
    assert json.loads(report_file.read_text(encoding="utf-8"))["agent_consumed_proven"] is False
