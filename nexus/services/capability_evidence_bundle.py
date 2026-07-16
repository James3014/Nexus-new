"""Shared capability evidence bundle (P2) — hash-sealed before Local/Online.

Produced after Planner + preflight invokers, before Local and Online stages.
Stub invokers must not count as real-invoked success.
SELECTED_NOT_EXECUTED must not count as success.
``immutable=True`` alone is never proof — consumers must re-verify bundle_hash.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


BUNDLE_SCHEMA = "nexus.capability_evidence_bundle.v1"
VERDICT_SCHEMA = "nexus.capability_evidence_bundle_verdict.v1"


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _canonical_payload_for_hash(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical body used to (re)compute bundle_hash — excludes bundle_hash itself."""
    payload = {k: copy.deepcopy(v) for k, v in bundle.items() if k != "bundle_hash"}
    return payload


def compute_bundle_hash(bundle: Mapping[str, Any]) -> str:
    """Re-canonicalize and hash the bundle body (consumer-side check)."""
    return _hash_json(_canonical_payload_for_hash(bundle))


def build_capability_evidence_bundle(
    *,
    task_id: str,
    workspace_revision: str,
    task_statement: str,
    plan_payload: Mapping[str, Any],
    plan_hash: str,
    planner_decision_id: str,
    capability_results: Mapping[str, Any],
    selected_capabilities: list[str] | tuple[str, ...],
    source_hash: str = "",
) -> dict[str, Any]:
    """Build hash-sealed shared evidence bundle for Local and Online consumers."""
    task_hash = hashlib.sha256(str(task_statement or "").encode("utf-8")).hexdigest()
    src_hash = str(source_hash or "").strip() or task_hash
    plan_h = str(plan_hash or _hash_json(plan_payload))
    decision_id = str(planner_decision_id or plan_h)
    selected = [str(x) for x in selected_capabilities]

    entries: list[dict[str, Any]] = []
    real_invoked: list[str] = []
    stub_invoked: list[str] = []
    skipped: list[dict[str, str]] = []
    failed: list[str] = []
    evidence_ids: list[str] = []

    for name in selected:
        key = str(name)
        stage = capability_results.get(key)
        if not isinstance(stage, Mapping):
            entries.append(
                {
                    "name": key,
                    "status": "PENDING_OR_STAGE_OWNED",
                    "invoked_real": False,
                    "invoked_stub": False,
                    "skipped": False,
                    "success": False,
                    "skip_reason": "",
                    "evidence_refs": [],
                    "evidence_ids": [],
                    "physical_callable": "",
                    "telemetry": {"token_usage": 0, "model_calls": 0},
                }
            )
            continue

        response = stage.get("response") if isinstance(stage.get("response"), Mapping) else {}
        skipped_flag = bool(stage.get("skipped")) or str(stage.get("status") or "") == "SKIPPED"
        if not skipped_flag and isinstance(response, Mapping):
            skipped_flag = bool(response.get("skipped"))
        stub_flag = bool(response.get("stub")) if isinstance(response, Mapping) else False
        if not stub_flag:
            stub_flag = bool(stage.get("stub"))
        invoked = bool(stage.get("invoked")) and not skipped_flag
        evidence_refs = [str(r) for r in (stage.get("evidence_refs") or [])]
        entry_evidence_ids = [
            str(r) for r in (stage.get("evidence_ids") or evidence_refs or [])
        ]
        skip_reason = str(
            stage.get("skip_reason")
            or stage.get("reason")
            or (response.get("skip_reason") if isinstance(response, Mapping) else "")
            or ""
        )
        physical = str(stage.get("physical_callable") or "")
        status = str(stage.get("status") or "")
        telemetry = _mapping(stage.get("telemetry"))
        if "token_usage" not in telemetry:
            telemetry["token_usage"] = int(stage.get("token_usage") or 0)
        if "model_calls" not in telemetry:
            telemetry["model_calls"] = int(stage.get("model_calls") or 0)

        if skipped_flag:
            success = False
            outcome = "SKIPPED"
            skipped.append({"name": key, "skip_reason": skip_reason or "explicit_skip"})
        elif invoked and stub_flag:
            success = False
            outcome = "STUB_INVOKED"
            stub_invoked.append(key)
        elif invoked and status == "SUCCEEDED" and evidence_refs and not stub_flag:
            success = True
            outcome = "REAL_INVOKED"
            real_invoked.append(key)
        elif invoked:
            success = False
            outcome = "INVOKED_NOT_SUCCESS"
            failed.append(key)
        else:
            success = False
            outcome = "SELECTED_NOT_EXECUTED"
            failed.append(key)

        for eid in entry_evidence_ids:
            if eid not in evidence_ids:
                evidence_ids.append(eid)

        entries.append(
            {
                "name": key,
                "status": outcome,
                "invoked_real": outcome == "REAL_INVOKED",
                "invoked_stub": outcome == "STUB_INVOKED",
                "skipped": skipped_flag,
                "success": success,
                "skip_reason": skip_reason if skipped_flag else "",
                "evidence_refs": evidence_refs,
                "evidence_ids": entry_evidence_ids,
                "physical_callable": physical,
                "stage_status": status,
                "telemetry": telemetry,
            }
        )

    baseline = {
        "task_id": str(task_id),
        "workspace_revision": str(workspace_revision),
        "task_statement_hash": task_hash,
        "source_hash": src_hash,
        "plan_hash": plan_h,
        "planner_decision_id": decision_id,
        "selected_capabilities": list(selected),
    }
    baseline_hash = _hash_json(baseline)

    bundle: dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "immutable": True,
        "task_id": str(task_id),
        "workspace_revision": str(workspace_revision),
        "task_statement_hash": task_hash,
        "source_hash": src_hash,
        "plan_hash": plan_h,
        "planner_decision_id": decision_id,
        "baseline_hash": baseline_hash,
        "selection_authority": "CapabilityPlanner",
        "selected_capabilities": list(selected),
        "entries": entries,
        "evidence_ids": evidence_ids,
        "summary": {
            "real_invoked": real_invoked,
            "stub_invoked": stub_invoked,
            "skipped": skipped,
            "failed_or_not_executed": failed,
            "real_success_count": len(real_invoked),
            "stub_does_not_count_as_success": True,
            "selected_not_executed_not_success": True,
        },
        "public_claim_allowed": False,
    }
    bundle["bundle_hash"] = compute_bundle_hash(bundle)
    return bundle


def verify_capability_evidence_bundle(bundle: Mapping[str, Any] | None) -> dict[str, Any]:
    """Public verifier: fail-closed on missing/tampered hash-sealed bundles.

    ``immutable=True`` alone is **not** sufficient proof.
    """
    blockers: list[str] = []
    if not isinstance(bundle, Mapping) or not bundle:
        return {
            "schema": VERDICT_SCHEMA,
            "ok": False,
            "gate_passed": False,
            "blockers": ["bundle_missing_or_not_mapping"],
            "bundle_hash": "",
            "expected_bundle_hash": "",
            "immutable_alone_insufficient": True,
        }

    if str(bundle.get("schema") or "") != BUNDLE_SCHEMA:
        blockers.append("schema_mismatch")

    claimed_hash = str(bundle.get("bundle_hash") or "")
    if not claimed_hash:
        blockers.append("bundle_hash_missing")

    recomputed = compute_bundle_hash(bundle)
    if claimed_hash and claimed_hash != recomputed:
        blockers.append("bundle_hash_mismatch")

    # Immutable flag is never enough by itself
    if bool(bundle.get("immutable")) and not claimed_hash:
        blockers.append("immutable_without_hash")
    if bool(bundle.get("immutable")) and claimed_hash and claimed_hash != recomputed:
        blockers.append("immutable_but_tampered")

    required_fields = (
        "task_id",
        "workspace_revision",
        "task_statement_hash",
        "source_hash",
        "plan_hash",
        "planner_decision_id",
        "selected_capabilities",
        "entries",
    )
    for field in required_fields:
        if field not in bundle:
            blockers.append(f"missing_field:{field}")

    selected = [str(x) for x in (bundle.get("selected_capabilities") or [])]
    entries = bundle.get("entries")
    if not isinstance(entries, list):
        blockers.append("entries_not_list")
        entries = []
    entry_names = {
        str(e.get("name")) for e in entries if isinstance(e, Mapping)
    }
    for name in selected:
        if name not in entry_names:
            blockers.append(f"missing_selected_entry:{name}")

    # Recompute baseline integrity
    baseline = {
        "task_id": str(bundle.get("task_id") or ""),
        "workspace_revision": str(bundle.get("workspace_revision") or ""),
        "task_statement_hash": str(bundle.get("task_statement_hash") or ""),
        "source_hash": str(bundle.get("source_hash") or ""),
        "plan_hash": str(bundle.get("plan_hash") or ""),
        "planner_decision_id": str(bundle.get("planner_decision_id") or ""),
        "selected_capabilities": selected,
    }
    expected_baseline = _hash_json(baseline)
    claimed_baseline = str(bundle.get("baseline_hash") or "")
    if claimed_baseline and claimed_baseline != expected_baseline:
        blockers.append("baseline_hash_mismatch")

    if bundle.get("public_claim_allowed") is True:
        blockers.append("public_claim_allowed_must_be_false")

    ok = not blockers
    return {
        "schema": VERDICT_SCHEMA,
        "ok": ok,
        "gate_passed": ok,
        "blockers": blockers,
        "bundle_hash": claimed_hash,
        "expected_bundle_hash": recomputed,
        "baseline_hash": claimed_baseline,
        "expected_baseline_hash": expected_baseline,
        "immutable_alone_insufficient": True,
        "public_claim_allowed": False,
    }


def consumer_view(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only deep copy for Local/Online — same root bundle_hash.

    Does not add annotation fields that would alter the sealed body hash.
    """
    return copy.deepcopy(dict(bundle))


def assert_consumer_bundle_intact(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Consumer pre-use check: re-canonicalize and require matching bundle_hash."""
    verdict = verify_capability_evidence_bundle(bundle)
    if not verdict["ok"]:
        return {
            "ok": False,
            "gate_passed": False,
            "blockers": list(verdict.get("blockers") or []),
            "bundle_hash": verdict.get("bundle_hash"),
            "expected_bundle_hash": verdict.get("expected_bundle_hash"),
        }
    # Presence of bundle without hash recheck is insufficient
    if not str(bundle.get("bundle_hash") or ""):
        return {
            "ok": False,
            "gate_passed": False,
            "blockers": ["consumer_missing_bundle_hash"],
            "bundle_hash": "",
            "expected_bundle_hash": compute_bundle_hash(bundle),
        }
    return {
        "ok": True,
        "gate_passed": True,
        "blockers": [],
        "bundle_hash": str(bundle.get("bundle_hash")),
        "expected_bundle_hash": verdict["expected_bundle_hash"],
    }


def assert_same_baseline(
    *,
    bundle: Mapping[str, Any],
    observed_baseline_hash: str,
) -> dict[str, Any]:
    expected = str(bundle.get("baseline_hash") or "")
    observed = str(observed_baseline_hash or "")
    return {
        "ok": bool(expected) and expected == observed,
        "expected_baseline_hash": expected,
        "observed_baseline_hash": observed,
    }


def assert_same_root_bundle_hash(
    *,
    local_bundle: Mapping[str, Any] | None,
    online_bundle: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Local and Online must share the same root bundle_hash."""
    lh = str((local_bundle or {}).get("bundle_hash") or "")
    oh = str((online_bundle or {}).get("bundle_hash") or "")
    return {
        "ok": bool(lh) and lh == oh,
        "local_bundle_hash": lh,
        "online_bundle_hash": oh,
    }


def record_consumption(
    *,
    bundle: Mapping[str, Any],
    consumer: str,
    consumed_evidence_ids: list[str] | tuple[str, ...],
    selected_capabilities: list[str] | tuple[str, ...] | None = None,
    physical_callable: str = "",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build consumer consumption receipt fields.

    Empty consumed_evidence_ids must never mark capability as consumed.
    """
    intact = assert_consumer_bundle_intact(bundle)
    # Reject empty / synthetic envelope IDs (bundle:<hash> is never real consumption).
    raw_ids = [str(x).strip() for x in consumed_evidence_ids if str(x).strip()]
    ids = [i for i in raw_ids if not i.startswith("bundle:")]
    # When entries exist, every consumed id must trace to a successful entry.
    entry_id_set: set[str] = set()
    entries = bundle.get("entries") if isinstance(bundle, Mapping) else None
    if isinstance(entries, list):
        for ent in entries:
            if not isinstance(ent, Mapping):
                continue
            if not bool(ent.get("success") or ent.get("invoked_real")):
                continue
            for eid in list(ent.get("evidence_ids") or []) + list(ent.get("evidence_refs") or []):
                s = str(eid).strip()
                if s:
                    entry_id_set.add(s)
        for eid in bundle.get("evidence_ids") or []:
            s = str(eid).strip()
            if s:
                entry_id_set.add(s)
        if entry_id_set:
            ids = [i for i in ids if i in entry_id_set]
    selected = [str(x) for x in (selected_capabilities or bundle.get("selected_capabilities") or [])]
    consumer_input = {
        "consumer": str(consumer),
        "bundle_hash": str(bundle.get("bundle_hash") or ""),
        "consumed_evidence_ids": ids,
        "selected_capabilities": selected,
        "physical_callable": str(physical_callable or ""),
        **(dict(extra) if isinstance(extra, Mapping) else {}),
    }
    consumer_input_hash = _hash_json(consumer_input)
    # Empty evidence IDs must never mark capability as consumed.
    consumed = bool(ids) and bool(intact.get("ok"))
    return {
        "bundle_hash": str(bundle.get("bundle_hash") or ""),
        "consumed_evidence_ids": ids,
        "selected_capabilities": selected,
        "physical_callable": str(physical_callable or ""),
        "consumer_input_hash": consumer_input_hash,
        "capability_consumed": consumed,
        "bundle_intact": bool(intact.get("ok")),
        "bundle_verify_blockers": list(intact.get("blockers") or []),
        "public_claim_allowed": False,
    }
