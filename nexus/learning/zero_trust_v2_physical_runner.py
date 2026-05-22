from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from nexus.learning.zero_trust_v2_clean_slate import build_baseline_sandwich
from nexus.learning.zero_trust_v2_physical_sandbox import run_macos_sandbox_probe
from nexus.learning.zero_trust_v2_promotion import evaluate_zero_trust_v2_promotion_candidate
from nexus.learning.zero_trust_v2_receipts import build_runtime_signed_receipt
from nexus.learning.zero_trust_v2_sandbox import validate_sandbox_attestation


def _arm_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (str(row.get("capability_id") or ""), str(row.get("source_skill_id") or row.get("skill_id") or ""))


def run_zero_trust_v2_physical_row(
    row: Mapping[str, Any],
    *,
    command: Sequence[str],
    signing_secret: str,
    run_id: str,
    promotion_credit_allowed: bool = False,
    workspace_files: dict[str, str] | None = None,
    baseline_command: Sequence[str] | None = None,
    sandbox_probe: Callable[..., dict[str, Any]] = run_macos_sandbox_probe,
) -> dict[str, Any]:
    arm_type = str(row.get("arm_type") or "")
    enriched = dict(row)
    enriched.setdefault("security_contract_version", "v2")
    enriched.setdefault("promotion_credit_source", "v2_only")

    if arm_type == "wrong_or_quarantined_skill_v2":
        enriched.update(
            {
                "execution_status": "BLOCKED_BY_POLICY",
                "negative_control_blocked_count": 1,
                "v2_evidence_count": 0,
            }
        )
        return enriched
    if arm_type == "capability_only_v2":
        enriched.update({"execution_status": "BASELINE_ONLY", "v2_evidence_count": 0})
        return enriched

    baseline_before = None
    baseline_after = None
    if baseline_command:
        baseline_before = sandbox_probe(baseline_command, signing_secret=signing_secret, workspace_files=workspace_files)
    probe = sandbox_probe(command, signing_secret=signing_secret, workspace_files=workspace_files)
    if baseline_command:
        baseline_after = sandbox_probe(baseline_command, signing_secret=signing_secret, workspace_files=workspace_files)
    sandbox_attestation = probe["sandbox_attestation"]
    sandbox_verdict = validate_sandbox_attestation(sandbox_attestation)
    baseline_before_hash = (
        baseline_before["sandbox_attestation"]["artifact_hash"] if baseline_before else sandbox_attestation["artifact_hash"]
    )
    baseline_after_hash = (
        baseline_after["sandbox_attestation"]["artifact_hash"] if baseline_after else sandbox_attestation["artifact_hash"]
    )
    clean_contract = build_baseline_sandwich(
        baseline_before_hash=baseline_before_hash,
        skill_arm_hash=sandbox_attestation["artifact_hash"],
        baseline_after_hash=baseline_after_hash,
    )
    receipt = build_runtime_signed_receipt(
        run_id=run_id,
        row_id=str(row.get("row_id") or ""),
        arm_id=arm_type,
        capability_id=str(row.get("capability_id") or ""),
        skill_id=str(row.get("skill_id") or ""),
        artifact_hash=sandbox_attestation["artifact_hash"],
        raw_observation=sandbox_attestation.get("raw_observation") or {},
        secret=signing_secret,
        observer_version="zero-trust-v2-physical-runner-v1",
    )
    evidence_pass = probe.get("promotion_eligible") is True and sandbox_verdict["status"] == "PASS"
    credit_pass = evidence_pass and promotion_credit_allowed
    enriched.update(
        {
            "execution_status": "PASS" if evidence_pass else "BLOCKED_BY_POLICY",
            "probe_only": not promotion_credit_allowed,
            "sandbox_attestation": sandbox_attestation,
            "sandbox_attestation_verdict": sandbox_verdict,
            "baseline_before_attestation": baseline_before["sandbox_attestation"] if baseline_before else None,
            "baseline_after_attestation": baseline_after["sandbox_attestation"] if baseline_after else None,
            **receipt,
            **clean_contract,
            "v2_evidence_count": 1 if credit_pass else 0,
            "v2_trust_mismatch_count": 0,
        }
    )
    return enriched


def run_zero_trust_v2_physical_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    command: Sequence[str],
    signing_secret: str,
    run_id: str,
    promotion_credit_allowed: bool = False,
    workspace_files_by_key: Mapping[tuple[str, str], dict[str, str]] | None = None,
    baseline_command: Sequence[str] | None = None,
    sandbox_probe: Callable[..., dict[str, Any]] = run_macos_sandbox_probe,
) -> list[dict[str, Any]]:
    executed = [
        run_zero_trust_v2_physical_row(
            row,
            command=command,
            signing_secret=signing_secret,
            run_id=run_id,
            promotion_credit_allowed=promotion_credit_allowed,
            workspace_files=(workspace_files_by_key or {}).get(_arm_key(row)),
            baseline_command=baseline_command,
            sandbox_probe=sandbox_probe,
        )
        for row in rows
    ]
    negative_blocks: dict[tuple[str, str], int] = defaultdict(int)
    for row in executed:
        if row.get("arm_type") == "wrong_or_quarantined_skill_v2" and row.get("execution_status") == "BLOCKED_BY_POLICY":
            negative_blocks[_arm_key(row)] += 1
    for row in executed:
        if row.get("arm_type") in {"candidate_skill_v2", "shadow_candidate_v2"}:
            row["negative_control_blocked_count"] = negative_blocks.get(_arm_key(row), 0)
            row["promotion_evaluation"] = evaluate_zero_trust_v2_promotion_candidate(row, min_v2_evidence_count=1)
    return executed
