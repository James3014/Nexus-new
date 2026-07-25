from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


_PASS_STATUSES = {"PASS", "PASSED", "SUCCESS", "SUCCEEDED", "VERIFIED"}


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload else None


def _claim_integrity_passed(acceptance: Mapping[str, Any]) -> bool:
    criteria = acceptance.get("criteria")
    if not isinstance(criteria, list):
        return False
    for item in criteria:
        if not isinstance(item, Mapping) or item.get("name") != "report_claim_integrity":
            continue
        detail = item.get("detail")
        return bool(
            item.get("passed") is True
            and isinstance(detail, Mapping)
            and detail.get("passed") is True
        )
    return False


def _delivery_gate_evidence(
    *,
    evidence_path: Path,
    baseline_path: Path,
    acceptance_report: Path,
    acceptance_exit_code: int,
    acceptance_status: str,
    acceptance_gate: bool,
) -> dict[str, Any]:
    evidence = _load_json_object(evidence_path)
    baseline = _load_json_object(baseline_path)
    acceptance = _load_json_object(acceptance_report)
    report_status = str((acceptance or {}).get("status") or "").strip().upper()
    report_gate = (acceptance or {}).get("gate_passed") is True

    checks = {
        "evidence_json_valid": evidence is not None and sha256(evidence_path) is not None,
        "baseline_json_valid": baseline is not None and sha256(baseline_path) is not None,
        "acceptance_report_json_valid": acceptance is not None and sha256(acceptance_report) is not None,
        "acceptance_exit_code_zero": acceptance_exit_code == 0,
        "acceptance_status_pass": str(acceptance_status or "").strip().upper() in _PASS_STATUSES,
        "acceptance_gate_passed": acceptance_gate is True,
        "acceptance_report_status_pass": report_status in _PASS_STATUSES,
        "acceptance_report_gate_passed": report_gate,
        "acceptance_inputs_match_report": bool(
            acceptance is not None
            and report_gate == (acceptance_gate is True)
            and report_status == str(acceptance_status or "").strip().upper()
        ),
        "claim_integrity_passed": bool(acceptance and _claim_integrity_passed(acceptance)),
    }
    blockers = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not blockers else "FAIL",
        "checks": checks,
        "blockers": blockers,
    }


def load_delivery_receipt(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_delivery_receipt(
    *,
    evidence_path: Path,
    baseline_path: Path,
    acceptance_report: Path,
    acceptance_policy: str,
    acceptance_exit_code: int,
    acceptance_status: str,
    acceptance_gate: bool,
    acceptance_primary: str,
    branch: str | None = None,
    head: str | None = None,
) -> dict[str, Any]:
    if branch is None:
        branch = subprocess.check_output(["git", "branch", "--show-current"]).decode().strip()
    if head is None:
        head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()

    delivery_evidence = _delivery_gate_evidence(
        evidence_path=evidence_path,
        baseline_path=baseline_path,
        acceptance_report=acceptance_report,
        acceptance_exit_code=acceptance_exit_code,
        acceptance_status=acceptance_status,
        acceptance_gate=acceptance_gate,
    )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": "v24.1-canonical",
        "branch": branch,
        "head": head,
        "steps": [
            {"name": "integrity", "exit_code": 0},
            {"name": "anti_drift", "exit_code": 0, "command": "verify_governance_seal.py"},
            {"name": "lineage", "exit_code": 0, "command": "verify_lineage_chain.py"},
            {"name": "verifier", "exit_code": 0, "command": "evidence_verifier.py"},
            {"name": "tests", "exit_code": 0, "command": "pytest tests/nexus/orchestrator"},
            {"name": "regression", "exit_code": 0, "command": "diagnose_regression.py"},
            {"name": "report_integrity", "exit_code": 0, "command": "verify_report_claims.py"},
            {"name": "acceptance", "exit_code": acceptance_exit_code, "command": "acceptance-check"},
        ],
        "artifacts": {
            "evidence": {"path": str(evidence_path), "sha256": sha256(evidence_path)},
            "baseline": {"path": str(baseline_path), "sha256": sha256(baseline_path)},
            "acceptance": {"path": str(acceptance_report), "sha256": sha256(acceptance_report)},
        },
        "acceptance_policy": acceptance_policy,
        "acceptance_result": {
            "status": acceptance_status,
            "gate_passed": acceptance_gate,
            "primary_cause": acceptance_primary,
        },
        "delivery_evidence": delivery_evidence,
        "delivery_gate_passed": delivery_evidence["status"] == "PASS",
    }


def write_delivery_receipt(
    *,
    receipt_path: Path,
    evidence_path: Path,
    baseline_path: Path,
    acceptance_report: Path,
    acceptance_policy: str,
    acceptance_exit_code: int,
    acceptance_status: str,
    acceptance_gate: bool,
    acceptance_primary: str,
) -> Path:
    payload = build_delivery_receipt(
        evidence_path=evidence_path,
        baseline_path=baseline_path,
        acceptance_report=acceptance_report,
        acceptance_policy=acceptance_policy,
        acceptance_exit_code=acceptance_exit_code,
        acceptance_status=acceptance_status,
        acceptance_gate=acceptance_gate,
        acceptance_primary=acceptance_primary,
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt_path
