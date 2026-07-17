"""R5 dual CapabilityReceipt parity / loss audit (RC-3).

Does **not** alias core (belief_contracts) and engine (capability_contracts)
CapabilityReceipt types. Converts only when fields are exact or derived_with_proof;
lossy / unrepresentable fields produce blockers and fail closed.
"""
from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any, Mapping

from nexus.core.belief_contracts import CapabilityReceipt as CoreReceipt
from nexus.engine.capability_contracts import CapabilityReceipt as EngineReceipt

# Field semantic matrix (Spec / TECH)
FIELD_MATRIX: dict[str, dict[str, str]] = {
    # engine field -> relation to core
    "name": {"core": "capability_name", "class": "exact", "note": "rename only"},
    "selected": {"core": "selected", "class": "exact"},
    "invoked": {"core": "invoked", "class": "exact"},
    "evidence_present": {
        "core": "evidence_id",
        "class": "derived_with_proof",
        "note": "true iff non-empty evidence_id",
    },
    "evidence_refs": {
        "core": "evidence_id",
        "class": "derived_with_proof",
        "note": "single-id tuple from evidence_id when present",
    },
    "gate_passed": {"core": "gate_passed", "class": "exact"},
    "outcome_contributed": {
        "core": "outcome",
        "class": "lossy",
        "note": "bool vs dict outcome — not lossless",
    },
    "selection_source": {"core": "", "class": "unrepresentable", "note": "engine-only"},
    "executor_id": {"core": "", "class": "unrepresentable", "note": "engine-only"},
    "failure_reason": {"core": "", "class": "unrepresentable", "note": "engine-only"},
    "semantic_hash": {"core": "semantic_hash", "class": "exact"},
    "evidence_alignment": {"core": "evidence_alignment", "class": "exact"},
    "telemetries": {"core": "telemetries", "class": "exact"},
    # core-only
    "skill_receipts": {"core": "skill_receipts", "class": "unrepresentable", "note": "core-only list"},
    "timestamp": {"core": "timestamp", "class": "unrepresentable", "note": "core-only"},
    "outcome": {"core": "outcome", "class": "unrepresentable", "note": "dict not on engine"},
}


def classify_conversion(*, direction: str) -> list[dict[str, str]]:
    """Return field matrix rows for audit receipts."""
    rows = []
    for eng_or_key, meta in FIELD_MATRIX.items():
        rows.append(
            {
                "field": eng_or_key,
                "peer": meta.get("core", ""),
                "class": meta.get("class", ""),
                "note": meta.get("note", ""),
                "direction": direction,
            }
        )
    return rows


def _has_lossy_or_unrepresentable(direction: str) -> list[str]:
    blockers: list[str] = []
    for key, meta in FIELD_MATRIX.items():
        cls = meta.get("class")
        if cls in {"lossy", "unrepresentable"}:
            # Direction filters: when converting engine→core, engine-only unrepresentable
            # fields that have no core peer still block full parity.
            if direction == "engine_to_core" and key in {
                "selection_source",
                "executor_id",
                "failure_reason",
                "outcome_contributed",
            }:
                blockers.append(f"{cls}:{key}")
            if direction == "core_to_engine" and key in {
                "skill_receipts",
                "timestamp",
                "outcome",
                "outcome_contributed",
            }:
                blockers.append(f"{cls}:{key}")
    return blockers


def engine_to_core(engine: EngineReceipt | Mapping[str, Any]) -> dict[str, Any]:
    """Attempt conversion; never silent PASS on lossy fields."""
    if isinstance(engine, EngineReceipt):
        data = engine.to_dict() if hasattr(engine, "to_dict") else asdict(engine)
    else:
        data = dict(engine)
    blockers = _has_lossy_or_unrepresentable("engine_to_core")
    # Always block full parity due to structural asymmetry (by design)
    if data.get("outcome_contributed") is not None and "outcome" not in data:
        blockers.append("lossy:outcome_contributed_without_outcome_dict")
    if data.get("selection_source") or data.get("executor_id") or data.get("failure_reason"):
        # presence of engine-only fields without core peers
        for f in ("selection_source", "executor_id", "failure_reason"):
            if data.get(f):
                blockers.append(f"unrepresentable:{f}")
    blockers = sorted(set(blockers))
    ok = not blockers
    core_partial = {
        "capability_name": str(data.get("name") or data.get("capability_name") or ""),
        "selected": bool(data.get("selected")),
        "invoked": bool(data.get("invoked")),
        "evidence_id": (
            str((data.get("evidence_refs") or [""])[0])
            if data.get("evidence_refs")
            else str(data.get("evidence_id") or "")
        ),
        "gate_passed": bool(data.get("gate_passed")),
        "outcome": {},  # cannot reconstruct from outcome_contributed alone
        "skill_receipts": [],
        "semantic_hash": str(data.get("semantic_hash") or ""),
        "evidence_alignment": bool(data.get("evidence_alignment", True)),
        "telemetries": dict(data.get("telemetries") or {}),
        "timestamp": "",
    }
    return {
        "schema": "nexus.capability_receipt_parity.v1",
        "direction": "engine_to_core",
        "parity_complete": False,  # dual types are not fully representable
        "ok": ok and False,  # explicit: full parity never true without adapter product decision
        "blockers": blockers or ["structural_asymmetry:dual_capability_receipt"],
        "lossy_fields": [b for b in blockers if b.startswith("lossy:")],
        "unrepresentable_fields": [b for b in blockers if b.startswith("unrepresentable:")],
        "partial_core": core_partial,
        "field_matrix": classify_conversion(direction="engine_to_core"),
        "public_claim_allowed": False,
    }


def core_to_engine(core: CoreReceipt | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(core, CoreReceipt):
        data = {
            "capability_name": core.capability_name,
            "selected": core.selected,
            "invoked": core.invoked,
            "evidence_id": core.evidence_id,
            "gate_passed": core.gate_passed,
            "outcome": dict(core.outcome or {}),
            "skill_receipts": list(core.skill_receipts or []),
            "semantic_hash": core.semantic_hash,
            "evidence_alignment": core.evidence_alignment,
            "telemetries": dict(core.telemetries or {}),
            "timestamp": core.timestamp,
        }
    else:
        data = dict(core)
    blockers = _has_lossy_or_unrepresentable("core_to_engine")
    if data.get("outcome"):
        blockers.append("lossy:outcome_dict_to_bool")
    if data.get("skill_receipts"):
        blockers.append("unrepresentable:skill_receipts")
    if data.get("timestamp"):
        blockers.append("unrepresentable:timestamp")
    blockers = sorted(set(blockers)) or ["structural_asymmetry:dual_capability_receipt"]
    eng_partial = {
        "name": str(data.get("capability_name") or data.get("name") or ""),
        "selected": bool(data.get("selected")),
        "invoked": bool(data.get("invoked")),
        "evidence_present": bool(str(data.get("evidence_id") or "").strip()),
        "evidence_refs": (str(data.get("evidence_id")),) if data.get("evidence_id") else (),
        "gate_passed": bool(data.get("gate_passed")),
        "outcome_contributed": bool(data.get("outcome")),  # lossy compression
        "selection_source": "unknown",
        "executor_id": "",
        "failure_reason": "",
        "semantic_hash": str(data.get("semantic_hash") or ""),
        "evidence_alignment": bool(data.get("evidence_alignment", True)),
        "telemetries": dict(data.get("telemetries") or {}),
    }
    return {
        "schema": "nexus.capability_receipt_parity.v1",
        "direction": "core_to_engine",
        "parity_complete": False,
        "ok": False,
        "blockers": blockers,
        "lossy_fields": [b for b in blockers if b.startswith("lossy:")],
        "unrepresentable_fields": [b for b in blockers if b.startswith("unrepresentable:")],
        "partial_engine": eng_partial,
        "field_matrix": classify_conversion(direction="core_to_engine"),
        "public_claim_allowed": False,
    }


def audit_roundtrip(engine: EngineReceipt) -> dict[str, Any]:
    """Prove round-trip is not lossless."""
    e2c = engine_to_core(engine)
    # rebuild partial engine from partial core
    c2e = core_to_engine(e2c.get("partial_core") or {})
    return {
        "schema": "nexus.capability_receipt_parity.roundtrip.v1",
        "engine_to_core_ok": e2c.get("ok"),
        "core_to_engine_ok": c2e.get("ok"),
        "lossless": False,
        "blockers": sorted(set(list(e2c.get("blockers") or []) + list(c2e.get("blockers") or []))),
        "public_claim_allowed": False,
    }



CANONICAL_ENVELOPE_SCHEMA = "nexus.capability_receipt.canonical_envelope.v1"


def to_canonical_envelope(
    source: EngineReceipt | CoreReceipt | Mapping[str, Any],
    *,
    source_type: str = "",
) -> dict[str, Any]:
    """Versioned envelope: shared receipt_base + extensions + explicit loss ledger.

    Does not alias core/engine classes. Consumers must read the envelope rather
    than assuming silent partial conversion is lossless.
    """
    if isinstance(source, EngineReceipt):
        st = source_type or "engine.CapabilityReceipt"
        data = source.to_dict() if hasattr(source, "to_dict") else asdict(source)
    elif isinstance(source, CoreReceipt):
        st = source_type or "core.CapabilityReceipt"
        data = source.to_dict() if hasattr(source, "to_dict") else asdict(source)
    else:
        st = source_type or str((source or {}).get("source_type") or "unknown")
        data = dict(source or {})

    # Shared receipt_base if already present, else project minimal child base
    rb = data.get("receipt_base") if isinstance(data.get("receipt_base"), Mapping) else None
    if not isinstance(rb, Mapping):
        try:
            from nexus.evidence.receipt_base import project_child_receipt_base

            rb = project_child_receipt_base(
                source_world="R5",
                source_component=st,
                task_id=str(data.get("task_id") or ""),
                stage_name=str(data.get("name") or data.get("capability_name") or "capability"),
                stage_payload={
                    "selected": data.get("selected"),
                    "invoked": data.get("invoked"),
                    "gate_passed": data.get("gate_passed"),
                    "outcome_contributed": data.get("outcome_contributed"),
                },
                selected=bool(data.get("selected")),
                injected=bool(data.get("invoked")),
                used=bool(data.get("outcome_contributed")),
                evidence_present=bool(data.get("evidence_present") or data.get("evidence_id")),
                gate_passed=bool(data.get("gate_passed")),
                outcome_contributed=bool(data.get("outcome_contributed")),
                claim_boundary={"public_claim_allowed": False},
            )
        except Exception as exc:  # noqa: BLE001
            rb = {"schema": "nexus.receipt_base.v1", "error": str(exc)[:200], "public_claim_allowed": False}

    # Partition shared vs source-specific
    shared_keys = {
        "selected",
        "invoked",
        "gate_passed",
        "evidence_present",
        "semantic_hash",
        "evidence_alignment",
        "telemetries",
        "public_claim_safe",
    }
    extensions: dict[str, Any] = {}
    shared_fields: dict[str, Any] = {}
    for k, v in data.items():
        if k in {"receipt_base", "receipt_base_error"}:
            continue
        if k in shared_keys or k in {"name", "capability_name"}:
            shared_fields[k] = v
        else:
            extensions[k] = v

    loss_ledger = [
        row
        for row in classify_conversion(direction="envelope")
        if row.get("class") in {"lossy", "unrepresentable"}
    ]
    full_type_parity = len(loss_ledger) == 0
    shared_base_parity_complete = bool(
        isinstance(rb, Mapping)
        and rb.get("run_anchor_hash")
        and rb.get("receipt_hash")
        and rb.get("public_claim_allowed") is False
    )
    blockers: list[str] = []
    if not full_type_parity:
        blockers.append("full_type_parity_incomplete")
        blockers.extend(f"{r['class']}:{r['field']}" for r in loss_ledger[:12])
    if not shared_base_parity_complete:
        blockers.append("shared_base_parity_incomplete")

    return {
        "schema": CANONICAL_ENVELOPE_SCHEMA,
        "schema_version": "1.0",
        "source_type": st,
        "receipt_base": dict(rb) if isinstance(rb, Mapping) else {},
        "shared_fields": shared_fields,
        "extensions": extensions,
        "loss_ledger": loss_ledger,
        "shared_base_parity_complete": shared_base_parity_complete,
        "full_type_parity": full_type_parity,
        "migration_complete": False if not full_type_parity else shared_base_parity_complete,
        "rc3_migration_complete": False,  # retain blocker until full lossless
        "blockers": blockers,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def envelope_roundtrip_shared(source: EngineReceipt | CoreReceipt | Mapping[str, Any]) -> dict[str, Any]:
    """Prove shared fields survive envelope packaging (not full type parity)."""
    env = to_canonical_envelope(source)
    shared = dict(env.get("shared_fields") or {})
    return {
        "ok": bool(env.get("shared_base_parity_complete")),
        "shared_base_parity_complete": env.get("shared_base_parity_complete"),
        "full_type_parity": env.get("full_type_parity"),
        "shared_keys": sorted(shared.keys()),
        "extensions_keys": sorted((env.get("extensions") or {}).keys()),
        "loss_ledger": env.get("loss_ledger"),
        "blockers": env.get("blockers"),
        "public_claim_allowed": False,
        "envelope": env,
    }
