"""Receipt base projection: JSON-safe dicts, run_anchor_hash, acyclic hash DAG.

RC-1 / Spec v2.1 execution rules:
- R3 remains a plain dict (no dataclass instances in receipts).
- Legacy top-level ``evidence_refs: list[str]`` stays; structured refs live under
  ``receipt_base.structured_evidence_refs`` (additive).
- Children bind to ``run_anchor_hash`` (immutable identity), never to the final
  R3 ``receipt_hash`` (avoids cyclic parent/child hashing).
- Reuses the same canonical JSON hashing style as evidence_sealing / zero_trust.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from nexus.evidence.claim_boundary import ClaimBoundary

RECEIPT_BASE_SCHEMA = "nexus.receipt_base.v1"
RECEIPT_BASE_SCHEMA_VERSION = "1.0"

# Fields hashed into the immutable run anchor (existing identity only).
_RUN_ANCHOR_KEYS = (
    "task_id",
    "workspace_revision",
    "planner_decision_id",
    "treatment_run_id",
    "packet_hash",
    "shared_bundle_hash",
    "selection_authority",
    "mainchain_route_version",
    "route_freeze",
    "mainchain_entry",
)


def canonical_json_hash(value: Any) -> str:
    """Deterministic SHA-256 over canonical JSON (sort_keys, compact separators).

    Same convention as ``nexus.contracts.evidence_sealing`` / zero_trust receipts.
    """
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_run_anchor_hash(
    *,
    task_id: str = "",
    workspace_revision: str = "",
    planner_decision_id: str = "",
    treatment_run_id: str = "",
    packet_hash: str = "",
    shared_bundle_hash: str = "",
    selection_authority: str = "CapabilityPlanner",
    mainchain_route_version: str = "",
    route_freeze: bool = False,
    mainchain_entry: bool = False,
) -> str:
    """Hash immutable run identity only (no stage outputs)."""
    payload = {
        "task_id": str(task_id or ""),
        "workspace_revision": str(workspace_revision or ""),
        "planner_decision_id": str(planner_decision_id or ""),
        "treatment_run_id": str(treatment_run_id or ""),
        "packet_hash": str(packet_hash or ""),
        "shared_bundle_hash": str(shared_bundle_hash or ""),
        "selection_authority": str(selection_authority or "CapabilityPlanner"),
        "mainchain_route_version": str(mainchain_route_version or ""),
        "route_freeze": bool(route_freeze),
        "mainchain_entry": bool(mainchain_entry),
    }
    return canonical_json_hash(payload)


def build_structured_evidence_ref(
    *,
    evidence_id: str,
    schema: str = "",
    content_hash: str = "",
    source: str = "",
    task_id: str = "",
    scope: str = "",
    timestamp: str = "",
) -> dict[str, Any]:
    """JSON-safe structured evidence reference.

    Empty content_hash → hash_status=UNAVAILABLE and claim_contribution=false.
    Never hash the id as a fake content hash.
    """
    eid = str(evidence_id or "").strip()
    ch = str(content_hash or "").strip()
    unavailable = not ch
    return {
        "evidence_id": eid,
        "schema": str(schema or ""),
        "content_hash": ch,
        "hash_status": "UNAVAILABLE" if unavailable else "PRESENT",
        "claim_contribution": False if unavailable else True,
        "source": str(source or ""),
        "task_id": str(task_id or ""),
        "scope": str(scope or ""),
        "timestamp": str(timestamp or ""),
    }


def legacy_evidence_refs_to_structured(
    refs: Sequence[Any] | None,
    *,
    task_id: str = "",
    source: str = "legacy_evidence_refs",
    scope: str = "shared",
) -> list[dict[str, Any]]:
    """Project legacy list[str] into structured refs without inventing content hashes."""
    out: list[dict[str, Any]] = []
    for item in refs or ():
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        out.append(
            build_structured_evidence_ref(
                evidence_id=text,
                schema="nexus.evidence_ref.legacy_string.v1",
                content_hash="",  # unknown — fail-closed for claim contribution
                source=source,
                task_id=task_id,
                scope=scope,
            )
        )
    return out


def build_consumption_chain_entry(
    *,
    capability: str,
    selected: bool = False,
    injected: bool = False,
    used: bool = False,
    evidence_present: bool = False,
    gate_passed: bool = False,
    outcome_contributed: bool = False,
    consumer: str = "",
) -> dict[str, Any]:
    return {
        "capability": str(capability or ""),
        "selected": bool(selected),
        "injected": bool(injected),
        "used": bool(used),
        "evidence_present": bool(evidence_present),
        "gate_passed": bool(gate_passed),
        "outcome_contributed": bool(outcome_contributed),
        "consumer": str(consumer or ""),
    }


def hash_stage_payload(stage: Mapping[str, Any] | None, *, stage_name: str) -> str:
    """Content hash for a stage/child payload (excludes final R3 receipt_hash)."""
    body = dict(stage or {})
    # Never let a nested receipt_hash of self influence (defensive)
    body.pop("receipt_hash", None)
    return canonical_json_hash({"stage": stage_name, "payload": body})


def compute_receipt_hash(
    *,
    run_anchor_hash: str,
    ordered_child_hashes: Sequence[str] = (),
    claim_boundary: Mapping[str, Any] | None = None,
    shared_bundle_hash: str = "",
    consumer_payload_hash: str = "",
    artifact_hash: str = "",
    source_candidate_hash: str = "",
    applied_candidate_hash: str = "",
    structured_evidence_refs: Sequence[Mapping[str, Any]] = (),
    consumption_chain: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Aggregate hash for a receipt node. Does not include the resulting hash itself."""
    payload = {
        "run_anchor_hash": str(run_anchor_hash or ""),
        "ordered_child_hashes": [str(h) for h in ordered_child_hashes],
        "claim_boundary": dict(claim_boundary or {}),
        "shared_bundle_hash": str(shared_bundle_hash or ""),
        "consumer_payload_hash": str(consumer_payload_hash or ""),
        "artifact_hash": str(artifact_hash or ""),
        "source_candidate_hash": str(source_candidate_hash or ""),
        "applied_candidate_hash": str(applied_candidate_hash or ""),
        "structured_evidence_refs": [dict(r) for r in structured_evidence_refs],
        "consumption_chain": [dict(c) for c in consumption_chain],
    }
    return canonical_json_hash(payload)


def claim_boundary_projection(
    claim_boundary: Mapping[str, Any] | ClaimBoundary | None = None,
) -> dict[str, Any]:
    """Always JSON-safe fail-closed claim boundary dict."""
    if isinstance(claim_boundary, ClaimBoundary):
        return claim_boundary.to_dict()
    if isinstance(claim_boundary, Mapping):
        # Re-parse through ClaimBoundary so producer True cannot unlock
        return ClaimBoundary.from_dict(dict(claim_boundary)).to_dict()
    return ClaimBoundary().to_dict()


def build_receipt_base_dict(
    *,
    schema: str = RECEIPT_BASE_SCHEMA,
    schema_version: str = RECEIPT_BASE_SCHEMA_VERSION,
    task_id: str = "",
    workspace_revision: str = "",
    planner_decision_id: str = "",
    treatment_run_id: str = "",
    packet_hash: str = "",
    run_anchor_hash: str = "",
    receipt_hash: str = "",
    parent_receipt_hashes: Sequence[str] = (),
    shared_bundle_hash: str = "",
    consumer_payload_hash: str = "",
    artifact_hash: str = "",
    source_candidate_hash: str = "",
    applied_candidate_hash: str = "",
    consumption_chain: Sequence[Mapping[str, Any]] = (),
    structured_evidence_refs: Sequence[Mapping[str, Any]] = (),
    claim_boundary: Mapping[str, Any] | ClaimBoundary | None = None,
    source_world: str = "",
    source_component: str = "",
    execution_topology: str = "",
    selection_authority: str = "CapabilityPlanner",
    mainchain_entry: bool = False,
    mainchain_route_version: str = "",
    route_freeze: bool = False,
    with_nexus_armor: bool = False,
    wall_time_ms: int | None = None,
    model_calls: int | None = None,
    total_tokens: int | None = None,
    timestamp: str = "",
) -> dict[str, Any]:
    """Build JSON-serializable receipt_base (no dataclass instances)."""
    cb = claim_boundary_projection(claim_boundary)
    parents = [str(p) for p in parent_receipt_hashes if str(p).strip()]
    return {
        "schema": str(schema or RECEIPT_BASE_SCHEMA),
        "schema_version": str(schema_version or RECEIPT_BASE_SCHEMA_VERSION),
        "task_id": str(task_id or ""),
        "workspace_revision": str(workspace_revision or ""),
        "planner_decision_id": str(planner_decision_id or ""),
        "treatment_run_id": str(treatment_run_id or ""),
        "packet_hash": str(packet_hash or ""),
        "run_anchor_hash": str(run_anchor_hash or ""),
        "receipt_hash": str(receipt_hash or ""),
        "parent_receipt_hashes": parents,
        "shared_bundle_hash": str(shared_bundle_hash or ""),
        "consumer_payload_hash": str(consumer_payload_hash or ""),
        "artifact_hash": str(artifact_hash or ""),
        "source_candidate_hash": str(source_candidate_hash or ""),
        "applied_candidate_hash": str(applied_candidate_hash or ""),
        "consumption_chain": [dict(c) for c in consumption_chain],
        "structured_evidence_refs": [dict(r) for r in structured_evidence_refs],
        "claim_boundary": cb,
        "public_claim_allowed": False,
        "production_ready": False,
        "source_world": str(source_world or ""),
        "source_component": str(source_component or ""),
        "execution_topology": str(execution_topology or ""),
        "selection_authority": str(selection_authority or "CapabilityPlanner"),
        "mainchain_entry": bool(mainchain_entry),
        "mainchain_route_version": str(mainchain_route_version or ""),
        "route_freeze": bool(route_freeze),
        "with_nexus_armor": bool(with_nexus_armor),
        "wall_time_ms": wall_time_ms,
        "model_calls": model_calls,
        "total_tokens": total_tokens,
        "timestamp": str(timestamp or datetime.now(timezone.utc).isoformat()),
    }


def attach_r3_receipt_base(
    receipt: dict[str, Any],
    *,
    stage_hashes: Sequence[str] | None = None,
    consumption_chain: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach additive ``receipt_base`` to an R3 receipt dict in place and return it.

    Preserves top-level ``evidence_refs`` (legacy list[str]).
    Final ``receipt_hash`` aggregates run_anchor + ordered child hashes; children
    must use ``run_anchor_hash`` as parent, not this final hash.
    """
    if not isinstance(receipt, dict):
        raise TypeError("R3 receipt must be a dict")

    task_id = str(receipt.get("task_id") or "")
    workspace_revision = str(receipt.get("workspace_revision") or "")
    planner = receipt.get("planner") if isinstance(receipt.get("planner"), Mapping) else {}
    planner_decision_id = str(
        receipt.get("planner_decision_id")
        or planner.get("planner_decision_id")
        or planner.get("decision_id")
        or ""
    )
    verified = receipt.get("verified_assist") if isinstance(receipt.get("verified_assist"), Mapping) else {}
    packet = verified.get("packet") if isinstance(verified.get("packet"), Mapping) else {}
    treatment_run_id = str(
        receipt.get("treatment_run_id")
        or packet.get("treatment_run_id")
        or ""
    )
    packet_hash = str(receipt.get("packet_hash") or packet.get("packet_hash") or verified.get("packet_hash") or "")
    bundle = receipt.get("capability_evidence_bundle")
    if isinstance(bundle, Mapping):
        shared_bundle_hash = str(
            receipt.get("shared_bundle_hash")
            or bundle.get("bundle_hash")
            or bundle.get("shared_bundle_hash")
            or canonical_json_hash(dict(bundle))
        )
    else:
        shared_bundle_hash = str(receipt.get("shared_bundle_hash") or "")

    selection_authority = str(receipt.get("selection_authority") or "CapabilityPlanner")
    mainchain_entry = bool(receipt.get("mainchain_entry", False))
    mainchain_route_version = str(receipt.get("mainchain_route_version") or "")
    route_freeze = bool(receipt.get("route_freeze", False))
    with_nexus_armor = bool(receipt.get("with_nexus_armor", False))

    run_anchor = compute_run_anchor_hash(
        task_id=task_id,
        workspace_revision=workspace_revision,
        planner_decision_id=planner_decision_id,
        treatment_run_id=treatment_run_id,
        packet_hash=packet_hash,
        shared_bundle_hash=shared_bundle_hash,
        selection_authority=selection_authority,
        mainchain_route_version=mainchain_route_version,
        route_freeze=route_freeze,
        mainchain_entry=mainchain_entry,
    )

    legacy_refs = receipt.get("evidence_refs")
    if not isinstance(legacy_refs, list):
        legacy_refs = list(legacy_refs or []) if legacy_refs else []
    structured = legacy_evidence_refs_to_structured(
        legacy_refs,
        task_id=task_id,
        source="unified_runtime.evidence_refs",
        scope="shared",
    )

    # Ordered child hashes: explicit stage_hashes or derive from local/online/capabilities
    children: list[str] = [str(h) for h in (stage_hashes or ()) if str(h).strip()]
    if not children:
        for name in ("local", "online", "verifier", "learning"):
            stage = receipt.get(name)
            if isinstance(stage, Mapping) and stage:
                children.append(hash_stage_payload(stage, stage_name=name))
        caps = receipt.get("capability_results")
        if isinstance(caps, Mapping):
            for cap_name in sorted(caps.keys()):
                stage = caps[cap_name]
                if isinstance(stage, Mapping):
                    children.append(hash_stage_payload(stage, stage_name=f"cap:{cap_name}"))

    claim = claim_boundary_projection(receipt.get("claim_boundary"))
    consumer_payload_hash = str(
        receipt.get("consumer_payload_hash")
        or canonical_json_hash(
            {
                "consumed_evidence_ids": receipt.get("consumed_evidence_ids") or [],
                "contributed_capabilities": receipt.get("contributed_capabilities") or [],
                "executed_capabilities": receipt.get("executed_capabilities") or [],
            }
        )
    )

    chain = [dict(c) for c in (consumption_chain or ())]
    if not chain:
        # Minimal chain from capability_results if present
        caps = receipt.get("capability_results")
        if isinstance(caps, Mapping):
            for cap_name in sorted(caps.keys()):
                stage = caps[cap_name]
                if not isinstance(stage, Mapping):
                    continue
                chain.append(
                    build_consumption_chain_entry(
                        capability=str(cap_name),
                        selected=True,
                        injected=bool(stage.get("invoked") or stage.get("injected")),
                        used=bool(stage.get("invoked") or stage.get("used")),
                        evidence_present=bool(stage.get("evidence_present") or stage.get("evidence_refs")),
                        gate_passed=bool(stage.get("gate_passed")),
                        outcome_contributed=bool(stage.get("outcome_contributed")),
                        consumer=str(stage.get("delegated_to") or stage.get("consumer") or ""),
                    )
                )

    # Verifier / candidate hashes if present on receipt
    artifact_hash = str(receipt.get("artifact_hash") or "")
    source_candidate_hash = str(receipt.get("source_candidate_hash") or "")
    applied_candidate_hash = str(receipt.get("applied_candidate_hash") or "")
    verifier = receipt.get("verifier") if isinstance(receipt.get("verifier"), Mapping) else {}
    if not artifact_hash and verifier:
        artifact_hash = str(verifier.get("artifact_hash") or "")
        if not artifact_hash:
            artifact_hash = hash_stage_payload(verifier, stage_name="verifier")

    r_hash = compute_receipt_hash(
        run_anchor_hash=run_anchor,
        ordered_child_hashes=children,
        claim_boundary=claim,
        shared_bundle_hash=shared_bundle_hash,
        consumer_payload_hash=consumer_payload_hash,
        artifact_hash=artifact_hash,
        source_candidate_hash=source_candidate_hash,
        applied_candidate_hash=applied_candidate_hash,
        structured_evidence_refs=structured,
        consumption_chain=chain,
    )

    # Final R3 parents = run anchor only (not self, not circular child binding)
    base = build_receipt_base_dict(
        task_id=task_id,
        workspace_revision=workspace_revision,
        planner_decision_id=planner_decision_id,
        treatment_run_id=treatment_run_id,
        packet_hash=packet_hash,
        run_anchor_hash=run_anchor,
        receipt_hash=r_hash,
        parent_receipt_hashes=[run_anchor],
        shared_bundle_hash=shared_bundle_hash,
        consumer_payload_hash=consumer_payload_hash,
        artifact_hash=artifact_hash,
        source_candidate_hash=source_candidate_hash,
        applied_candidate_hash=applied_candidate_hash,
        consumption_chain=chain,
        structured_evidence_refs=structured,
        claim_boundary=claim,
        source_world="A",
        source_component="unified_runtime",
        selection_authority=selection_authority,
        mainchain_entry=mainchain_entry,
        mainchain_route_version=mainchain_route_version,
        route_freeze=route_freeze,
        with_nexus_armor=with_nexus_armor,
    )
    # Record ordered children for audit (not a second identity system)
    base["ordered_child_hashes"] = list(children)

    receipt["receipt_base"] = base
    receipt["run_anchor_hash"] = run_anchor
    receipt["receipt_hash"] = r_hash
    # Never flip public claim
    receipt["public_claim_allowed"] = False
    if "claim_boundary" in receipt and isinstance(receipt["claim_boundary"], dict):
        receipt["claim_boundary"]["public_claim_allowed"] = False
    return receipt


def assert_json_safe(obj: Any, *, path: str = "root") -> None:
    """Raise TypeError if obj cannot be JSON-serialized with default json.dumps."""
    try:
        json.dumps(obj, ensure_ascii=False, sort_keys=True, default=_strict_default)
    except TypeError as exc:
        raise TypeError(f"not JSON-safe at {path}: {exc}") from exc


def _strict_default(o: Any) -> Any:
    raise TypeError(f"non-JSON type: {type(o)!r}")


def project_child_receipt_base(
    *,
    source_world: str,
    source_component: str,
    task_id: str = "",
    workspace_revision: str = "",
    planner_decision_id: str = "",
    treatment_run_id: str = "",
    packet_hash: str = "",
    shared_bundle_hash: str = "",
    selection_authority: str = "CapabilityPlanner",
    mainchain_route_version: str = "",
    route_freeze: bool = False,
    mainchain_entry: bool = False,
    with_nexus_armor: bool = False,
    stage_payload: Mapping[str, Any] | None = None,
    stage_name: str = "child",
    evidence_refs: Sequence[Any] = (),
    consumer: str = "",
    selected: bool = True,
    injected: bool = False,
    used: bool = False,
    evidence_present: bool = False,
    gate_passed: bool = False,
    outcome_contributed: bool = False,
    artifact_hash: str = "",
    source_candidate_hash: str = "",
    applied_candidate_hash: str = "",
    claim_boundary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build JSON-safe receipt_base for R1/R2 (parent = run_anchor only; acyclic)."""
    run_anchor = compute_run_anchor_hash(
        task_id=task_id,
        workspace_revision=workspace_revision,
        planner_decision_id=planner_decision_id,
        treatment_run_id=treatment_run_id,
        packet_hash=packet_hash,
        shared_bundle_hash=shared_bundle_hash,
        selection_authority=selection_authority,
        mainchain_route_version=mainchain_route_version,
        route_freeze=route_freeze,
        mainchain_entry=mainchain_entry,
    )
    stage_hash = hash_stage_payload(stage_payload or {}, stage_name=stage_name)
    structured = legacy_evidence_refs_to_structured(
        evidence_refs,
        task_id=task_id,
        source=source_component,
        scope=source_world or "child",
    )
    chain = [
        build_consumption_chain_entry(
            capability=stage_name,
            selected=selected,
            injected=injected,
            used=used,
            evidence_present=evidence_present,
            gate_passed=gate_passed,
            outcome_contributed=outcome_contributed,
            consumer=consumer,
        )
    ]
    consumer_payload_hash = canonical_json_hash(
        {
            "stage": stage_name,
            "used": used,
            "injected": injected,
            "evidence_refs": [str(r) for r in evidence_refs],
        }
    )
    r_hash = compute_receipt_hash(
        run_anchor_hash=run_anchor,
        ordered_child_hashes=[stage_hash],
        claim_boundary=claim_boundary_projection(claim_boundary),
        shared_bundle_hash=shared_bundle_hash,
        consumer_payload_hash=consumer_payload_hash,
        artifact_hash=artifact_hash,
        source_candidate_hash=source_candidate_hash,
        applied_candidate_hash=applied_candidate_hash,
        structured_evidence_refs=structured,
        consumption_chain=chain,
    )
    base = build_receipt_base_dict(
        task_id=task_id,
        workspace_revision=workspace_revision,
        planner_decision_id=planner_decision_id,
        treatment_run_id=treatment_run_id,
        packet_hash=packet_hash,
        run_anchor_hash=run_anchor,
        receipt_hash=r_hash,
        parent_receipt_hashes=[run_anchor],
        shared_bundle_hash=shared_bundle_hash,
        consumer_payload_hash=consumer_payload_hash,
        artifact_hash=artifact_hash or stage_hash,
        source_candidate_hash=source_candidate_hash,
        applied_candidate_hash=applied_candidate_hash,
        consumption_chain=chain,
        structured_evidence_refs=structured,
        claim_boundary=claim_boundary,
        source_world=source_world,
        source_component=source_component,
        selection_authority=selection_authority,
        mainchain_entry=mainchain_entry,
        mainchain_route_version=mainchain_route_version,
        route_freeze=route_freeze,
        with_nexus_armor=with_nexus_armor,
    )
    base["stage_hash"] = stage_hash
    return base


def stamp_r1_local_response(
    response: Any,
    *,
    request: Any = None,
) -> Any:
    """Additive stamp LocalModelExecutorResponse.raw_model_metadata['receipt_base']."""
    if response is None:
        return response
    meta = getattr(response, "raw_model_metadata", None)
    if not isinstance(meta, dict):
        return response
    req = request
    task_id = ""
    planner_decision_id = ""
    workspace_revision = ""
    shared_bundle_hash = ""
    if req is not None:
        task_id = str(getattr(req, "task_id", None) or (getattr(req, "planner_snapshot", {}) or {}).get("task_id") or "")
        snap = getattr(req, "planner_snapshot", None)
        if isinstance(snap, Mapping):
            task_id = task_id or str(snap.get("task_id") or "")
            planner_decision_id = str(snap.get("planner_decision_id") or snap.get("decision_id") or "")
            workspace_revision = str(snap.get("workspace_revision") or "")
            shared_bundle_hash = str(snap.get("shared_bundle_hash") or "")
        task_id = task_id or str(getattr(req, "instance_id", "") or "")
    candidate_hash = str(getattr(response, "candidate_hash", "") or "")
    evidence_refs = tuple(getattr(response, "evidence_refs", ()) or ())
    invoked = bool(getattr(response, "invoked", False))
    called = bool(getattr(response, "local_model_called", False))
    provider = str(getattr(response, "provider", "") or "")
    model_name = str(getattr(response, "model_name", "") or "")
    error = str(getattr(response, "error", "") or "")
    auth_blocked = (not called) and (
        "provider_not_configured" in error
        or "not_configured" in error
        or provider in {"none", "", "inert"}
    )
    stage_payload = {
        "invoked": invoked,
        "local_model_called": called,
        "candidate_hash": candidate_hash,
        "provider": provider,
        "model_name": model_name,
        "error": error,
        "auth_blocked": auth_blocked,
        "evidence_refs": list(evidence_refs),
    }
    base = project_child_receipt_base(
        source_world="C",
        source_component="local_executor",
        task_id=task_id,
        workspace_revision=workspace_revision,
        planner_decision_id=planner_decision_id,
        shared_bundle_hash=shared_bundle_hash,
        stage_payload=stage_payload,
        stage_name="local_model_executor",
        evidence_refs=evidence_refs,
        consumer="local",
        selected=True,
        injected=invoked,
        used=called and not auth_blocked,
        evidence_present=bool(evidence_refs) or bool(candidate_hash),
        gate_passed=bool(called and not error and not auth_blocked),
        outcome_contributed=bool(called and candidate_hash and not error),
        artifact_hash=candidate_hash,
        source_candidate_hash=candidate_hash,
        applied_candidate_hash=candidate_hash if called else "",
        claim_boundary={"public_claim_allowed": False, "auth_blocked": auth_blocked},
    )
    if auth_blocked:
        base["auth_status"] = "AUTH_BLOCKED"
        base["auth_reason"] = error or "provider_not_configured"
    meta["receipt_base"] = base
    meta["run_anchor_hash"] = base["run_anchor_hash"]
    meta["receipt_hash"] = base["receipt_hash"]
    meta["public_claim_allowed"] = False
    return response


def stamp_r2_hybrid_meta(
    result: Any,
    *,
    task_id: str = "",
    planner_decision_id: str = "",
    workspace_revision: str = "",
    shared_bundle_hash: str = "",
) -> dict[str, Any]:
    """Build HybridStageResult.to_meta() overlay with additive receipt_base."""
    if hasattr(result, "to_meta"):
        meta = dict(result.to_meta())
    elif isinstance(result, Mapping):
        meta = dict(result)
    else:
        meta = {}
    stages = meta.get("hybrid_stages") if isinstance(meta.get("hybrid_stages"), Mapping) else {}
    candidate_identity = str(meta.get("candidate_identity") or "")
    selected_hash = str(
        (meta.get("cloud_payload") or {}).get("selected_hash")
        if isinstance(meta.get("cloud_payload"), Mapping)
        else ""
    ) or candidate_identity
    applied_hash = candidate_identity
    live_ok = bool(meta.get("live_evidence_allowed"))
    stage_payload = {
        "status": meta.get("hybrid_stage_status") or meta.get("status"),
        "live_evidence_allowed": live_ok,
        "block_reason": meta.get("live_evidence_block_reason") or meta.get("block_reason"),
        "stages": stages,
        "selected_hash_matches_applied": meta.get("selected_hash_matches_applied"),
        "semantic_correctness_passed": meta.get("semantic_correctness_passed"),
        "hidden_verifier_passed": meta.get("hidden_verifier_passed"),
        "infra_invalid": meta.get("infra_invalid"),
    }
    base = project_child_receipt_base(
        source_world="hybrid",
        source_component="hybrid_runtime",
        task_id=task_id,
        workspace_revision=workspace_revision,
        planner_decision_id=planner_decision_id,
        shared_bundle_hash=shared_bundle_hash,
        stage_payload=stage_payload,
        stage_name="cloud_with_local_assist",
        evidence_refs=[],
        consumer="hybrid",
        selected=True,
        injected=True,
        used=live_ok,
        evidence_present=live_ok,
        gate_passed=bool(meta.get("hidden_verifier_passed")),
        outcome_contributed=bool(meta.get("semantic_correctness_passed")),
        artifact_hash=applied_hash,
        source_candidate_hash=selected_hash,
        applied_candidate_hash=applied_hash if meta.get("selected_hash_matches_applied") else "",
        claim_boundary={
            "public_claim_allowed": False,
            "live_evidence_allowed": live_ok,
            "block_reason": str(meta.get("live_evidence_block_reason") or ""),
        },
    )
    # Stage hashes for cloud/local legs
    cloud_hash = hash_stage_payload(meta.get("cloud_payload") or {}, stage_name="hybrid_cloud")
    local_hash = hash_stage_payload(stages, stage_name="hybrid_local_stages")
    base["cloud_stage_hash"] = cloud_hash
    base["local_stage_hash"] = local_hash
    meta["receipt_base"] = base
    meta["run_anchor_hash"] = base["run_anchor_hash"]
    meta["receipt_hash"] = base["receipt_hash"]
    meta["public_claim_allowed"] = False
    # Preserve legacy fields
    return meta
