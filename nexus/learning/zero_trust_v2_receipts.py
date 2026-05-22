from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping


def canonical_json_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_runtime_signed_receipt(
    *,
    run_id: str,
    row_id: str,
    arm_id: str,
    capability_id: str,
    skill_id: str,
    artifact_hash: str,
    raw_observation: Mapping[str, Any],
    secret: str,
    observer_version: str = "mock-v1",
) -> dict[str, Any]:
    raw_observation_hash = canonical_json_hash(raw_observation)
    signature_inputs = {
        "run_id": run_id,
        "row_id": row_id,
        "arm_id": arm_id,
        "capability_id": capability_id,
        "skill_id": skill_id,
        "artifact_hash": artifact_hash,
        "raw_observation_hash": raw_observation_hash,
    }
    receipt_hash = canonical_json_hash(signature_inputs)
    signature = hmac.new(secret.encode("utf-8"), receipt_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "receipt_provenance": "runtime_signed",
        "receipt_signature": signature,
        "receipt_signature_algorithm": "hmac-sha256",
        "receipt_signature_inputs": {**signature_inputs, "receipt_hash": receipt_hash},
        "observer": {"issuer": "nexus.runtime_observer", "version": observer_version},
    }


def verify_runtime_signed_receipt(receipt: Mapping[str, Any], *, secret: str) -> bool:
    if receipt.get("receipt_provenance") != "runtime_signed":
        return False
    if receipt.get("receipt_signature_algorithm") != "hmac-sha256":
        return False
    inputs = receipt.get("receipt_signature_inputs")
    if not isinstance(inputs, Mapping):
        return False
    receipt_hash = str(inputs.get("receipt_hash") or "")
    if not receipt_hash:
        return False
    expected = hmac.new(secret.encode("utf-8"), receipt_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(receipt.get("receipt_signature") or ""))


def stamp_runtime_signed_behavior_bundle(
    bundle: Mapping[str, Any],
    *,
    run_id: str,
    capability_id: str,
    skill_id: str,
    secret: str,
    observer_version: str = "zero-trust-v2-behavior-hook-v1",
) -> dict[str, Any]:
    row_counts = bundle.get("row_counts") if isinstance(bundle.get("row_counts"), Mapping) else {}
    rubric = bundle.get("rubric_contract") if isinstance(bundle.get("rubric_contract"), Mapping) else {}
    with_rubric = rubric.get("with_nexus") if isinstance(rubric.get("with_nexus"), Mapping) else {}
    hard_failures = list(with_rubric.get("hard_fail_reasons") or [])
    eligible_rows = int(row_counts.get("eligible_with_nexus") or 0)
    infra_invalid_rows = int(row_counts.get("infra_invalid_with_nexus") or 0)
    blockers: list[str] = []
    if eligible_rows <= 0:
        blockers.append("no_eligible_behavior_row")
    if infra_invalid_rows > 0:
        blockers.append("infra_invalid_behavior_row")
    blockers.extend(str(item) for item in hard_failures if str(item))
    if blockers:
        return {"status": "BLOCKED", "blockers": sorted(set(blockers)), "bundle": dict(bundle)}

    raw_files = bundle.get("raw_files") if isinstance(bundle.get("raw_files"), Mapping) else {}
    with_file = raw_files.get("with_nexus") if isinstance(raw_files.get("with_nexus"), Mapping) else {}
    artifact_hash = str(with_file.get("sha256") or canonical_json_hash(bundle))
    raw_observation = {
        "row_counts": dict(row_counts),
        "raw_files": dict(raw_files),
        "rubric_contract": dict(rubric),
        "run_identity": bundle.get("run_identity") if isinstance(bundle.get("run_identity"), Mapping) else {},
        "task_manifest": bundle.get("task_manifest") if isinstance(bundle.get("task_manifest"), Mapping) else {},
    }
    receipt = build_runtime_signed_receipt(
        run_id=run_id,
        row_id=f"{run_id}:with_nexus",
        arm_id="candidate_skill_v2",
        capability_id=capability_id,
        skill_id=skill_id,
        artifact_hash=artifact_hash,
        raw_observation=raw_observation,
        secret=secret,
        observer_version=observer_version,
    )
    stamped = dict(bundle)
    stamped["zero_trust_v2_runtime_receipt"] = receipt
    stamped["zero_trust_v2_runtime_receipt_export"] = {
        "status": "PASS",
        "observer_version": observer_version,
        "capability_id": capability_id,
        "skill_id": skill_id,
        "artifact_hash": artifact_hash,
    }
    return {"status": "PASS", "blockers": [], "bundle": stamped, "receipt": receipt}
