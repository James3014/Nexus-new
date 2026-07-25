"""Fail-closed validator for live-proof receipts.

Only ``evidence_mode="live_runtime"`` may receive ``LIVE_PROOF_PASS``.
Canary, fixture, simulation, harness, unknown, and missing modes fail closed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


LIVE_PROOF_PASS = "LIVE_PROOF_PASS"
LIVE_PROOF_FAIL = "LIVE_PROOF_FAIL"
LIVE_PROOF_NOT_RUN = "LIVE_PROOF_NOT_RUN"


@dataclass
class LiveProofResult:
    status: str
    reason: str = ""
    failures: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    claim_boundary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "nexus.local_assist.live_proof.v1",
            "status": self.status,
            "reason": self.reason,
            "failures": list(self.failures),
            "evidence": dict(self.evidence),
            "claim_boundary": dict(self.claim_boundary),
        }


def _load_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(data) if isinstance(data, Mapping) else {}


def _valid_sha256(value: str) -> bool:
    if not value:
        return False
    clean = value.lower().replace("sha256:", "")
    if len(clean) != 64:
        return False
    return all(c in "0123456789abcdef" for c in clean)


def validate_live_proof(
    *,
    pipeline_report: Mapping[str, Any] | None = None,
    unified_runtime_receipt: Mapping[str, Any] | None = None,
    pipeline_report_path: str | Path | None = None,
    unified_runtime_receipt_path: str | Path | None = None,
    external_authorized: bool | None = None,
    evidence_mode: str | None = None,
) -> LiveProofResult:
    """Validate durable pipeline report + Unified Runtime receipt for live proof.

    Fail-closed: missing fields and uninvoked stages produce LIVE_PROOF_FAIL.
    When external runtime is not authorized and no real receipts exist,
    returns LIVE_PROOF_NOT_RUN.

    Only ``evidence_mode="live_runtime"`` may receive ``LIVE_PROOF_PASS``.
    """
    import os

    report = dict(pipeline_report or _load_json(pipeline_report_path))
    receipt = dict(unified_runtime_receipt or _load_json(unified_runtime_receipt_path))
    authorized = (
        external_authorized
        if external_authorized is not None
        else os.environ.get("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "").strip() == "1"
    )

    claim = {
        "public_claim_allowed": False,
        "production_ready": False,
        "value_measured": False,
    }

    if not receipt and not report:
        return LiveProofResult(
            status=LIVE_PROOF_NOT_RUN,
            reason="external_runtime_not_authorized" if not authorized else "receipts_missing",
            failures=["pipeline_report_missing", "unified_runtime_receipt_missing"],
            evidence={"external_authorized": authorized},
            claim_boundary=claim,
        )

    if not authorized and not receipt:
        return LiveProofResult(
            status=LIVE_PROOF_NOT_RUN,
            reason="external_runtime_not_authorized",
            failures=[],
            evidence={"external_authorized": False},
            claim_boundary=claim,
        )

    failures: list[str] = []
    if not receipt:
        failures.append("unified_runtime_receipt_missing")
    # Report is optional when receipt is present
    if not receipt and not report:
        failures.append("pipeline_report_missing")

    # Evidence mode check
    mode = str(evidence_mode or receipt.get("evidence_mode") or report.get("evidence_mode") or "").strip().lower()
    if not mode:
        mode = "unknown"
    if mode != "live_runtime":
        failures.append(f"non_live_evidence_mode:{mode}")

    local = receipt.get("local", {}) if isinstance(receipt.get("local"), Mapping) else {}
    online = receipt.get("online", {}) if isinstance(receipt.get("online"), Mapping) else {}
    local_resp = local.get("response", {}) if isinstance(local.get("response"), Mapping) else {}
    online_resp = online.get("response", {}) if isinstance(online.get("response"), Mapping) else {}

    task_id = str(receipt.get("task_id") or report.get("unified_runtime_task_id") or report.get("task_name") or "")
    revision = str(receipt.get("workspace_revision") or report.get("workspace_revision") or "")
    report_task = str(report.get("unified_runtime_task_id") or report.get("task_name") or "")
    report_rev = str(report.get("workspace_revision") or "")

    if task_id and report_task and task_id != report_task and report_task not in task_id and task_id not in report_task:
        failures.append("task_id_mismatch")
    if revision and report_rev and revision != report_rev:
        failures.append("workspace_revision_mismatch")
    if not task_id:
        failures.append("task_id_missing")
    if not revision:
        failures.append("workspace_revision_missing")

    if not bool(local.get("invoked")):
        failures.append("local_not_invoked")
    if not bool(local.get("gate_passed") or local_resp.get("output_delivered") or local.get("status") == "SUCCEEDED"):
        failures.append("local_output_not_delivered")
    if not bool(online.get("invoked") or online_resp.get("invoked")):
        failures.append("online_not_invoked")
    if not bool(online.get("gate_passed") or online_resp.get("output_delivered") or online.get("status") == "SUCCEEDED"):
        failures.append("online_output_not_delivered")

    local_calls = int(local_resp.get("provider_call_count") or local.get("provider_call_count") or 0)
    if local_calls < 1:
        failures.append("local_provider_call_count_lt_1")

    online_calls = int(online_resp.get("provider_call_count") or 0)
    if online_calls < 1:
        failures.append("online_provider_call_count_lt_1")

    evidence_refs = list(online.get("evidence_refs") or []) + list(online_resp.get("evidence_refs") or [])
    forwarded = bool(report.get("local_context_forwarded")) or any(
        "local_context_forwarded" in str(ref) for ref in evidence_refs
    )
    if not forwarded:
        failures.append("local_context_not_forwarded")

    formal_mutated = bool(report.get("formal_workspace_mutated") or receipt.get("formal_workspace_mutated"))
    if formal_mutated:
        failures.append("formal_workspace_mutated")

    # Verifier check
    verifier = receipt.get("verifier", {}) if isinstance(receipt.get("verifier"), Mapping) else {}
    if not bool(verifier.get("invoked")):
        failures.append("verifier_not_invoked")
    if not bool(verifier.get("gate_passed")):
        failures.append("verifier_gate_not_passed")

    # Receipt completeness
    if receipt and not bool(receipt.get("receipt_complete")):
        failures.append("receipt_incomplete")
    if receipt and str(receipt.get("terminal_status") or "").upper() != "SUCCEEDED":
        failures.append("receipt_terminal_status_not_succeeded")

    receipt_path = str(
        report.get("unified_runtime_receipt_path")
        or unified_runtime_receipt_path
        or receipt.get("receipt_path")
        or ""
    )
    if receipt_path:
        if not Path(receipt_path).is_file() and not receipt:
            failures.append("receipt_not_persisted")
    elif not receipt:
        failures.append("receipt_not_persisted")

    evidence = {
        "task_id": task_id,
        "workspace_revision": revision,
        "evidence_mode": mode,
        "local_invoked": bool(local.get("invoked")),
        "online_invoked": bool(online.get("invoked") or online_resp.get("invoked")),
        "local_provider_call_count": local_calls,
        "online_provider_call_count": online_calls,
        "local_context_forwarded": forwarded,
        "formal_workspace_mutated": formal_mutated,
        "receipt_path": receipt_path,
        "external_authorized": authorized,
    }

    if failures:
        if not authorized and (
            "unified_runtime_receipt_missing" in failures or "local_not_invoked" in failures
        ):
            return LiveProofResult(
                status=LIVE_PROOF_NOT_RUN,
                reason="external_runtime_not_authorized",
                failures=failures,
                evidence=evidence,
                claim_boundary=claim,
            )
        return LiveProofResult(
            status=LIVE_PROOF_FAIL,
            reason="live_proof_checks_failed",
            failures=failures,
            evidence=evidence,
            claim_boundary=claim,
        )

    # All checks passed, but only live_runtime gets PASS
    if mode != "live_runtime":
        return LiveProofResult(
            status=LIVE_PROOF_NOT_RUN,
            reason=f"non_live_evidence_mode:{mode}",
            failures=[],
            evidence=evidence,
            claim_boundary=claim,
        )

    return LiveProofResult(
        status=LIVE_PROOF_PASS,
        reason="local_and_online_invocations_verified",
        failures=[],
        evidence=evidence,
        claim_boundary={**claim, "real_local_online_continuation_observed": True},
    )


def write_live_proof_result(path: str | Path, result: LiveProofResult | Mapping[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict() if isinstance(result, LiveProofResult) else dict(result)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return destination
