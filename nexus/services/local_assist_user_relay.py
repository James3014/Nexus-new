"""Fail-closed validation for human-relayed external Agent responses."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PACKAGE_SCHEMA = "nexus.local_assist.user_relay_package.v1"
RESPONSE_SCHEMA = "nexus.local_assist.user_relay_response.v1"
SUCCESS_STATUS = "AGENT_OPERATED_LOCAL_ASSIST_PROVEN_WITH_USER_RELAY"
IMPORTABLE_RESPONSE_STATUSES = {"IMPORTED", "IMPORTED_PENDING_VALIDATION"}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json_object_required")
    return payload


def _resolve_relative(root: Path, raw: Any, *, field: str, blockers: list[str]) -> Path | None:
    value = str(raw or "")
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        blockers.append(f"{field}_must_be_relative:{value}")
        return None
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        blockers.append(f"{field}_outside_repo:{value}")
        return None
    return resolved


def _receipt_summary(
    *, root: Path, raw_ref: Any, blockers: list[str]
) -> dict[str, Any] | None:
    path = _resolve_relative(root, raw_ref, field="receipt_ref", blockers=blockers)
    if path is None:
        return None
    if not path.is_file():
        blockers.append(f"receipt_missing:{raw_ref}")
        return None
    try:
        receipt = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        blockers.append(f"receipt_invalid:{raw_ref}")
        return None
    if receipt.get("receipt_complete") is not True:
        blockers.append(f"receipt_incomplete:{raw_ref}")
    if receipt.get("provider") != "ollama":
        blockers.append(f"receipt_provider_not_ollama:{raw_ref}")
    if int(receipt.get("provider_call_count", 0) or 0) < 1:
        blockers.append(f"receipt_without_provider_call:{raw_ref}")
    boundary = receipt.get("claim_boundary", {})
    if boundary.get("runtime_invoked") is not True:
        blockers.append(f"receipt_runtime_not_invoked:{raw_ref}")
    if boundary.get("output_delivered") is not True:
        blockers.append(f"receipt_output_not_delivered:{raw_ref}")
    return {
        "ref": str(raw_ref),
        "task_id": str(receipt.get("task_id", "")),
        "provider": str(receipt.get("provider", "")),
        "resolved_model": str(receipt.get("resolved_model", "")),
        "receipt_complete": receipt.get("receipt_complete") is True,
    }


def validate_user_relay(
    *,
    package_file: str | Path,
    repo_root: str | Path,
    response_file: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a package and, when supplied, a user-imported Agent response.

    This function never sends data externally. Missing response is a valid
    preparation state and remains ``USER_RELAY_REQUIRED``.
    """
    root = Path(repo_root).resolve()
    blockers: list[str] = []
    try:
        package = _read_json(Path(package_file))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "REJECTED",
            "blockers": [f"package_invalid:{exc}"],
            "automated_exfiltration": False,
            "agent_output_imported": False,
            "agent_consumed_proven": False,
        }

    if package.get("schema") != PACKAGE_SCHEMA:
        blockers.append("unsupported_package_schema")
    if package.get("external_delivery_mode") != "human_relay":
        blockers.append("delivery_mode_not_human_relay")
    if package.get("delivery_authority") != "user":
        blockers.append("delivery_authority_not_user")
    if package.get("automated_exfiltration") is not False:
        blockers.append("automated_exfiltration_must_be_false")
    if package.get("local_assist_receipt_present") is not True:
        blockers.append("local_assist_receipt_missing")

    summaries: list[dict[str, Any]] = []
    for ref in package.get("local_assist_receipt_refs", ()) or ():
        summary = _receipt_summary(root=root, raw_ref=ref, blockers=blockers)
        if summary is not None:
            summaries.append(summary)

    base = {
        "schema": RESPONSE_SCHEMA,
        "task_id": str(package.get("task_id", "")),
        "external_delivery_mode": "human_relay",
        "delivery_authority": "user",
        "automated_exfiltration": False,
        "local_assist_receipt_present": bool(summaries) and not blockers,
        "receipt_summaries": summaries,
        "agent_output_imported": False,
        "agent_consumed_proven": False,
        "outcome_contributed": False,
        "value_measured": False,
        "claim_boundary": {
            "outcome_contributed": False,
            "value_measured": False,
        },
    }
    if blockers:
        base.update(status="REJECTED", blockers=sorted(set(blockers)))
        return base
    if response_file is None:
        base.update(status="USER_RELAY_REQUIRED", blockers=["user_relay_response_missing"])
        return base

    try:
        response = _read_json(Path(response_file))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        base.update(status="REJECTED", blockers=[f"response_invalid:{exc}"])
        return base

    if response.get("schema") != RESPONSE_SCHEMA:
        blockers.append("unsupported_response_schema")
    response_status = str(response.get("status", ""))
    if response_status not in IMPORTABLE_RESPONSE_STATUSES:
        blockers.append("response_status_not_importable")
    if response.get("external_delivery_mode") != "human_relay":
        blockers.append("response_delivery_mode_not_human_relay")
    if response.get("delivery_authority") != "user":
        blockers.append("response_delivery_authority_not_user")
    if response.get("automated_exfiltration") is not False:
        blockers.append("response_automated_exfiltration_must_be_false")
    if response_status == "IMPORTED" and response.get("agent_output_imported") is not True:
        blockers.append("response_not_marked_imported")
    if response.get("outcome_contributed") is True:
        blockers.append("response_outcome_contributed_must_be_false")
    if response.get("value_measured") is True:
        blockers.append("response_value_measured_must_be_false")
    response_claim_boundary = response.get("claim_boundary", {}) or {}
    if response_claim_boundary.get("outcome_contributed") is True:
        blockers.append("response_claim_boundary_outcome_must_be_false")
    if response_claim_boundary.get("value_measured") is True:
        blockers.append("response_claim_boundary_value_must_be_false")

    allowed_files = {
        str(value) for value in package.get("allowed_modified_files", ()) or ()
    }
    modified_files = response.get("modified_files", ()) or ()
    for raw_file in modified_files:
        _resolve_relative(root, raw_file, field="modified_file", blockers=blockers)
        if str(raw_file) not in allowed_files:
            blockers.append(f"modified_file_not_allowed:{raw_file}")
    if package.get("verifier_required") is True and response.get("verifier_result") != "pass":
        blockers.append("verifier_not_passed")

    evidence = "\n".join(
        [
            *(str(item) for item in response.get("agent_consumption_evidence", ()) or ()),
            str(response.get("final_output", "")),
            str(response.get("external_agent_response", "")),
        ]
    )
    for summary in summaries:
        identities = (summary["ref"], summary["task_id"], Path(summary["ref"]).name)
        if not any(identity and identity in evidence for identity in identities):
            blockers.append(f"missing_receipt_reference:{summary['task_id']}")

    base.update(
        {
            "agent_output_imported": not blockers,
            "agent_consumed_proven": not blockers,
            "modified_files": list(modified_files),
            "verifier_result": str(response.get("verifier_result", "")),
        }
    )
    if blockers:
        base.update(status="REJECTED", blockers=sorted(set(blockers)))
    else:
        base.update(status=SUCCESS_STATUS, blockers=[])
    return base


def write_user_relay_report(
    *,
    package_file: str | Path,
    repo_root: str | Path,
    response_file: str | Path | None,
    report_file: str | Path,
) -> dict[str, Any]:
    report = validate_user_relay(
        package_file=package_file,
        repo_root=repo_root,
        response_file=response_file,
    )
    output = Path(report_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
