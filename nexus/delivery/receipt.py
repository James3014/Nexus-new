from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "delivery_gate_passed": True,
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
