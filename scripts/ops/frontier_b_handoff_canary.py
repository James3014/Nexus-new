"""Read-only validator for the recorded Frontier B cross-session handoff canary.

This module consumes a durable canary receipt. It owns no task state and grants
no scheduling, routing, mutation, merge, release, deployment, or retry authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

CANARY_SCHEMA = "nexus.frontier_b.cross_session_canary.v1"
CHECKPOINT_SCHEMA = "nexus.runtime.workflow_checkpoint.v1"
CLAIM_CEILING = "WORKFLOW_HARDENING_ACCEPTANCE_EVIDENCE_ONLY"
CHECKPOINT_CLAIM_CEILING = "RUNTIME_SESSION_CHECKPOINT_EXECUTION_STATE_ONLY"


class CanaryError(ValueError):
    """The durable canary receipt is missing, stale, or tampered."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CanaryError(f"{field} must be non-empty")
    return value.strip()


def _git_revision(value: Any, field: str) -> str:
    text = _text(value, field)
    if not text.startswith("git-commit:"):
        raise CanaryError(f"{field} must use git-commit:<sha>")
    sha = text.removeprefix("git-commit:")
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
        raise CanaryError(f"{field} must bind an exact lowercase Git SHA")
    return text


def _validate_checkpoint(checkpoint: Mapping[str, Any]) -> None:
    if checkpoint.get("schema") != CHECKPOINT_SCHEMA:
        raise CanaryError("checkpoint schema mismatch")
    if checkpoint.get("claim_ceiling") != CHECKPOINT_CLAIM_CEILING:
        raise CanaryError("checkpoint claim ceiling mismatch")
    for field in ("task_id", "operation_id", "attempt_id", "next_gate"):
        _text(checkpoint.get(field), f"checkpoint.{field}")
    identity = checkpoint.get("identity")
    if not isinstance(identity, Mapping):
        raise CanaryError("checkpoint identity missing")
    _text(identity.get("repository"), "checkpoint.identity.repository")
    _git_revision(identity.get("source_revision"), "checkpoint.identity.source_revision")
    _text(identity.get("runtime_identity"), "checkpoint.identity.runtime_identity")
    if checkpoint.get("status") != "RUNNING":
        raise CanaryError("recorded cross-session canary must remain non-terminal")
    effects = checkpoint.get("completed_effects")
    if not isinstance(effects, list) or not effects:
        raise CanaryError("checkpoint must record completed side effects")
    seen: set[str] = set()
    for effect in effects:
        if not isinstance(effect, Mapping):
            raise CanaryError("completed effect must be an object")
        key = _text(effect.get("effect_key"), "completed_effect.effect_key")
        _text(effect.get("receipt_ref"), "completed_effect.receipt_ref")
        if key in seen:
            raise CanaryError("duplicate completed effect key")
        seen.add(key)
    material = dict(checkpoint)
    supplied_hash = material.pop("checkpoint_hash", None)
    if supplied_hash != _sha256(material):
        raise CanaryError("checkpoint hash mismatch")


def validate_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    receipt = dict(value)
    if receipt.get("schema") != CANARY_SCHEMA:
        raise CanaryError("canary schema mismatch")
    if receipt.get("claim_ceiling") != CLAIM_CEILING:
        raise CanaryError("canary claim ceiling mismatch")
    if receipt.get("chat_memory_required") is not False:
        raise CanaryError("chat memory cannot be a durable canary input")

    durable_inputs = receipt.get("durable_inputs")
    if durable_inputs != [
        "github_issue",
        "machine_readable_checkpoint",
        "exact_git_runtime_identities",
        "receipt_refs",
    ]:
        raise CanaryError("durable input contract mismatch")

    checkpoint = receipt.get("checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise CanaryError("checkpoint missing")
    _validate_checkpoint(checkpoint)

    owners = receipt.get("owner_contracts")
    if not isinstance(owners, list) or len(owners) != 7:
        raise CanaryError("exactly seven owner contracts are required")
    repos: set[str] = set()
    for owner in owners:
        if not isinstance(owner, Mapping):
            raise CanaryError("owner contract must be an object")
        repo = _text(owner.get("repository"), "owner.repository")
        if repo in repos:
            raise CanaryError("duplicate owner repository")
        repos.add(repo)
        if owner.get("issue_state") != "CLOSED" or owner.get("pr_state") != "MERGED":
            raise CanaryError("owner contract is not terminal")
        _git_revision(
            "git-commit:" + _text(owner.get("merge_sha"), "owner.merge_sha"), "owner.merge_sha"
        )

    policy = receipt.get("required_vs_advisory")
    if not isinstance(policy, Mapping):
        raise CanaryError("required/advisory evidence missing")
    required = policy.get("required_gates")
    advisory = policy.get("advisory_observers")
    if not isinstance(required, list) or not required:
        raise CanaryError("required gate evidence missing")
    if not isinstance(advisory, list) or not advisory:
        raise CanaryError("advisory observer evidence missing")
    if set(required) & set(advisory):
        raise CanaryError("required and advisory checks must be disjoint")
    if policy.get("advisory_failure_blocks_merge") is not False:
        raise CanaryError("advisory observer cannot gain merge authority")

    doctor = receipt.get("doctor")
    if not isinstance(doctor, Mapping) or doctor.get("read_only") is not True:
        raise CanaryError("workflow doctor read-only evidence missing")
    if doctor.get("schema") != "nexus.workflow_doctor.v1":
        raise CanaryError("workflow doctor schema mismatch")

    deployment = receipt.get("deployment_closeout_path")
    if not isinstance(deployment, Mapping):
        raise CanaryError("deployment closeout path missing")
    expected_steps = [
        "exact_merged_sha",
        "bundle_hash",
        "host_identity",
        "installed_identity",
        "loaded_identity",
        "bounded_canary",
        "rollback_receipt",
    ]
    if deployment.get("steps") != expected_steps:
        raise CanaryError("deployment closeout path incomplete")

    material = dict(receipt)
    supplied_hash = material.pop("content_sha256", None)
    if supplied_hash != _sha256(material):
        raise CanaryError("canary content hash mismatch")
    return receipt


def load_receipt(path: str | Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise CanaryError("unable to read canary receipt") from exc
    if not isinstance(raw, dict):
        raise CanaryError("canary receipt must be an object")
    return validate_receipt(raw)


def recover_from_receipt(
    receipt: Mapping[str, Any], *, current_source_revision: str
) -> dict[str, Any]:
    """Recover one non-terminal workflow using only durable receipt fields."""
    validated = validate_receipt(receipt)
    checkpoint = validated["checkpoint"]
    source = _git_revision(current_source_revision, "current_source_revision")
    expected_source = checkpoint["identity"]["source_revision"]
    drift = source != expected_source
    effects = [
        {
            "effect_key": row["effect_key"],
            "receipt_ref": row["receipt_ref"],
            "replay_allowed": False,
        }
        for row in checkpoint["completed_effects"]
    ]
    result = {
        "schema": "nexus.frontier_b.cross_session_recovery.v1",
        "task_id": checkpoint["task_id"],
        "operation_id": checkpoint["operation_id"],
        "attempt_id": checkpoint["attempt_id"],
        "phase": checkpoint["phase"],
        "next_gate": checkpoint["next_gate"],
        "source_revision": expected_source,
        "current_source_revision": source,
        "completed_effects": effects,
        "completed_effects_replay_allowed": False,
        "chat_memory_required": False,
        "resume_disposition": "RECONCILE" if drift else "SAFE",
        "reason": "SOURCE_IDENTITY_DRIFT" if drift else "EXACT_DURABLE_IDENTITY",
        "claim_ceiling": CLAIM_CEILING,
    }
    result["recovery_sha256"] = _sha256(result)
    return result


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Frontier B cross-session handoff canary"
    )
    parser.add_argument("receipt")
    parser.add_argument("--current-source", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = recover_from_receipt(
        load_receipt(args.receipt),
        current_source_revision=args.current_source,
    )
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result["resume_disposition"], result["next_gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
