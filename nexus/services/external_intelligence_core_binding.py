"""Pure Core ``repository_mutation_binding`` minting for External Intelligence fanout.

The Open SWE worker runtime admits an ``external_execution_envelope.v2`` only when it
carries a ``repository_mutation_binding`` that pins repository/source/workspace
identity, the owner-chosen execution lane, a capability-discovery receipt and a Core
acceptance contract.  Nexus keeps the semantic envelope immutable and derives a
per-attempt *bound* envelope (``semantic ∪ {repository_mutation_binding}``).

Two canonicalizations exist and must never be mixed:

* Core canonical JSON (``ensure_ascii=True``, ``allow_nan=False``) for Core hashes
  (``binding_hash``, ``acceptance_contract_hash``, ``authority_hash`` ...);
* envelope canonical JSON (``ensure_ascii=False``) for envelope digests that the
  runtime compares against the prompt ``envelope_sha256``.

The binding is non-authoritative transport evidence.  It does not grant routing,
admission, acceptance, integration or merge authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from nexus.services.external_intelligence import (
    ENVELOPE_SCHEMA_V2,
    ExternalIntelligenceError,
    parse_external_execution_envelope_v2,
)

CORE_MUTATION_BINDING_SCHEMA = "nexus.repository_mutation_binding.v1"
CORE_PROTOCOL_VERSION = "0.1.0-experimental"
CAPABILITY_DISCOVERY_RECEIPT_SCHEMA = "nexus.capability_discovery_receipt.v1"
CAPABILITY_DISCOVERY_INDEX_SCHEMA = "nexus.capability_discovery_index.v1"
CAPABILITY_DISCOVERY_INDEX_PATH = "docs/agents/CAPABILITY_DISCOVERY_INDEX.v1.json"
OPERATING_MODE_PATH = "docs/governance/current_operating_mode.yaml"
BOUND_OPERATION_SCHEMA = "nexus.eia.open_swe_operation.v2"
INTEGRATION_AUTHORITY_DOMAIN = "nexus.eia.integration-authority.v1"
ACCEPTANCE_REQUIREMENTS_DOMAIN = "nexus.eia.acceptance-requirements.v1"
BINDING_KEY = "repository_mutation_binding"
WORKSPACE_MODE = "managed_worktree"
DELETION_POLICY = "FORBID"
FRESHNESS_MARGIN_SECONDS = 120
# Upper bound of ExternalIntelligenceClosureRuntime.max_repairs_per_unit.
MAX_REPAIRS_PER_UNIT_LIMIT = 20
# Closure's built-in integrity checks (whitespace, deletions, scope): one git diff
# each, each bounded by this timeout, run once for the unit verification and once
# for the whole-task verification of every closure cycle.  The closure module reads
# its integrity git timeout from here so these checks stay counted if it changes.
# Not counted: closure's other git calls (``_run_git``, 30 s timeout each: HEAD,
# status, diff and composition probes), which FRESHNESS_MARGIN_SECONDS only
# partly absorbs, so the window can still under-count a worst-case cycle.
CLOSURE_INTEGRITY_CHECK_COUNT = 3
CLOSURE_INTEGRITY_GIT_TIMEOUT_SECONDS = 30.0
CLOSURE_INTEGRITY_SCOPES_PER_CYCLE = 2
CLOSURE_INTEGRITY_CYCLE_SECONDS = (
    CLOSURE_INTEGRITY_CHECK_COUNT
    * CLOSURE_INTEGRITY_GIT_TIMEOUT_SECONDS
    * CLOSURE_INTEGRITY_SCOPES_PER_CYCLE
)
EXECUTION_LANES = frozenset({"DIRECT_CANONICAL", "DIRECT_DELEGATED", "GOVERNED"})
CAPABILITY_DISPOSITIONS = frozenset({
    "REUSE_EXISTING",
    "EXTEND_EXISTING",
    "WRAP_EXISTING",
    "NEW_CAPABILITY_JUSTIFIED",
    "BLOCKED_UNKNOWN",
})
# CAPABILITY_DISCOVERY_GATE.md: a mutating worker must never start BLOCKED_UNKNOWN.
MUTATING_CAPABILITY_DISPOSITIONS = CAPABILITY_DISPOSITIONS - {"BLOCKED_UNKNOWN"}
DONOR_CAPABILITY_DISPOSITIONS = frozenset({"REUSE_EXISTING", "EXTEND_EXISTING", "WRAP_EXISTING"})

_BINDING_KEYS = frozenset({
    "schema",
    "binding_id",
    "operation_id",
    "attempt_id",
    "repository",
    "integration_authority",
    "capability_discovery",
    "core",
    "freshness",
    "binding_hash",
})
_REPOSITORY_KEYS = frozenset({
    "canonical_id",
    "origin",
    "source_revision",
    "source_tree",
    "workspace_identity",
    "workspace_mode",
})
_AUTHORITY_KEYS = frozenset({"execution_lane", "authority_ref", "authority_hash"})
_DISCOVERY_KEYS = frozenset({"required", "receipt_hash", "index_revision"})
_CORE_KEYS = frozenset({"protocol_version", "acceptance_contract", "acceptance_contract_hash"})
_FRESHNESS_KEYS = frozenset({"created_at", "valid_until", "revalidate_before_first_effect"})
_ACCEPTANCE_KEYS = frozenset({
    "contract_id",
    "requirements_hash",
    "required_verifier_ids",
    "allowed_paths",
    "deletion_policy",
})
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PREFIXED_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^git-commit:[0-9a-f]{40}$")
_GIT_TREE_RE = re.compile(r"^git-tree:[0-9a-f]{40}$")
_CAPABILITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")


class CoreBindingError(RuntimeError):
    """Fail-closed Core binding error; the message is a bounded reason code."""


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


def core_canonical_json(value: Any) -> str:
    """Core protocol transport canonical JSON (mirrors runtime ``_core_canonical_json``)."""
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def core_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(core_canonical_json(value).encode("utf-8")).hexdigest()


def envelope_canonical_json(value: Any) -> str:
    """Envelope canonical JSON (mirrors runtime ``_canonical_json``; ``ensure_ascii=False``)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def envelope_sha256(value: Any) -> str:
    return hashlib.sha256(envelope_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mirror_acceptance_contract_hash(contract: Mapping[str, Any]) -> str:
    return core_hash([
        contract["contract_id"],
        contract["requirements_hash"],
        sorted(contract["required_verifier_ids"]),
        sorted(contract["allowed_paths"]),
        contract["deletion_policy"],
    ])


def acceptance_contract_hash(contract: Mapping[str, Any]) -> str:
    """Delegate to the public Core protocol when importable; otherwise mirror it.

    The mirror is the exact five-item legacy (no expected-subjects universe) shape
    used by the runtime ``_core_acceptance_contract_hash``.
    """
    try:
        from product.protocol.generic_verification import (  # type: ignore[import-not-found]
            acceptance_contract_hash as _core_acceptance_contract_hash,
        )
    except Exception:  # Core is an optional sibling distribution.
        return _mirror_acceptance_contract_hash(contract)
    try:
        delegated = str(_core_acceptance_contract_hash(dict(contract)))
    except Exception:
        return _mirror_acceptance_contract_hash(contract)
    mirrored = _mirror_acceptance_contract_hash(contract)
    if delegated != mirrored:
        raise CoreBindingError("CORE_ACCEPTANCE_CONTRACT_HASH_DIVERGENCE")
    return delegated


# ---------------------------------------------------------------------------
# Authority inputs carried from the Issue contract / Task Card to fanout
# ---------------------------------------------------------------------------


def _verifier_rows(value: Any, field: str) -> tuple[tuple[str, tuple[str, ...], float], ...]:
    if not isinstance(value, (list, tuple)):
        raise CoreBindingError(f"CORE_AUTHORITY_{field}_INVALID")
    rows: list[tuple[str, tuple[str, ...], float]] = []
    for row in value:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise CoreBindingError(f"CORE_AUTHORITY_{field}_INVALID")
        verifier_id, argv, timeout = row
        if (
            not isinstance(verifier_id, str)
            or not verifier_id.strip()
            or not isinstance(argv, (list, tuple))
            or not argv
            or any(not isinstance(part, str) or not part for part in argv)
            or isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
        ):
            raise CoreBindingError(f"CORE_AUTHORITY_{field}_INVALID")
        rows.append((verifier_id, tuple(argv), float(timeout)))
    return tuple(rows)


@dataclass(frozen=True)
class CoreAuthorityInputs:
    """Owner/Issue authority inputs; parsed lazily so non-bound paths never fail on them."""

    repository: str
    issue_number: int
    revision: str
    intent: str
    issue_contract_sha256: str
    item_identity_hash: str
    task_id: str
    task_card_ref: str
    task_card_hash: str
    main_sha: str
    execution_lane: str
    capability_disposition: str
    capability_ids: tuple[str, ...] | None
    capability_justification: str
    unit_verifiers: Mapping[str, tuple[tuple[str, tuple[str, ...], float], ...]]
    whole_verifiers: tuple[tuple[str, tuple[str, ...], float], ...]
    worker_binding_sha256: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "issue_number": self.issue_number,
            "revision": self.revision,
            "intent": self.intent,
            "issue_contract_sha256": self.issue_contract_sha256,
            "item_identity_hash": self.item_identity_hash,
            "task_id": self.task_id,
            "task_card_ref": self.task_card_ref,
            "task_card_hash": self.task_card_hash,
            "main_sha": self.main_sha,
            "execution_lane": self.execution_lane,
            "capability_disposition": self.capability_disposition,
            "capability_ids": None if self.capability_ids is None else list(self.capability_ids),
            "capability_justification": self.capability_justification,
            "unit_verifiers": {
                unit_id: [[row[0], list(row[1]), row[2]] for row in rows]
                for unit_id, rows in sorted(self.unit_verifiers.items())
            },
            "whole_verifiers": [[row[0], list(row[1]), row[2]] for row in self.whole_verifiers],
            "worker_binding_sha256": self.worker_binding_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Any) -> "CoreAuthorityInputs":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise CoreBindingError("CORE_AUTHORITY_REQUIRED")
        text_fields = (
            "repository",
            "revision",
            "issue_contract_sha256",
            "item_identity_hash",
            "task_id",
            "task_card_ref",
            "task_card_hash",
            "main_sha",
            "worker_binding_sha256",
        )
        for key in text_fields:
            if not isinstance(value.get(key), str) or not value[key].strip():
                raise CoreBindingError(f"CORE_AUTHORITY_{key.upper()}_INVALID")
        issue_number = value.get("issue_number")
        if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number < 1:
            raise CoreBindingError("CORE_AUTHORITY_ISSUE_NUMBER_INVALID")
        for key in ("issue_contract_sha256", "item_identity_hash", "worker_binding_sha256"):
            if not _SHA256_RE.fullmatch(value[key]):
                raise CoreBindingError(f"CORE_AUTHORITY_{key.upper()}_INVALID")
        if not _SHA256_RE.fullmatch(value["task_card_hash"].lower()):
            raise CoreBindingError("CORE_AUTHORITY_TASK_CARD_HASH_INVALID")
        if not _SHA1_RE.fullmatch(value["main_sha"]):
            raise CoreBindingError("CORE_AUTHORITY_MAIN_SHA_INVALID")
        raw_ids = value.get("capability_ids")
        if raw_ids is not None and (
            not isinstance(raw_ids, (list, tuple))
            or any(not isinstance(item, str) for item in raw_ids)
        ):
            raise CoreBindingError("CORE_AUTHORITY_CAPABILITY_IDS_INVALID")
        raw_units = value.get("unit_verifiers")
        if not isinstance(raw_units, Mapping):
            raise CoreBindingError("CORE_AUTHORITY_UNIT_VERIFIERS_INVALID")
        return cls(
            repository=value["repository"],
            issue_number=issue_number,
            revision=value["revision"],
            intent=str(value.get("intent") or ""),
            issue_contract_sha256=value["issue_contract_sha256"],
            item_identity_hash=value["item_identity_hash"],
            task_id=value["task_id"],
            task_card_ref=value["task_card_ref"],
            task_card_hash=value["task_card_hash"].lower(),
            main_sha=value["main_sha"],
            execution_lane=str(value.get("execution_lane") or ""),
            capability_disposition=str(value.get("capability_disposition") or ""),
            capability_ids=None if raw_ids is None else tuple(raw_ids),
            capability_justification=str(value.get("capability_justification") or ""),
            unit_verifiers={
                str(unit_id): _verifier_rows(rows, "UNIT_VERIFIERS")
                for unit_id, rows in raw_units.items()
            },
            whole_verifiers=_verifier_rows(value.get("whole_verifiers"), "WHOLE_VERIFIERS"),
            worker_binding_sha256=value["worker_binding_sha256"],
        )


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _require_lane(execution_lane: str) -> str:
    lane = str(execution_lane or "").strip()
    if not lane:
        raise CoreBindingError("CORE_EXECUTION_LANE_REQUIRED")
    if lane not in EXECUTION_LANES:
        raise CoreBindingError("CORE_EXECUTION_LANE_INVALID")
    return lane


def _load_capability_index(index_bytes: bytes | None) -> set[str]:
    if index_bytes is None:
        raise CoreBindingError("CAPABILITY_DISCOVERY_INDEX_MISSING")
    try:
        index = json.loads(index_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CoreBindingError("CAPABILITY_DISCOVERY_INDEX_INVALID") from exc
    if not isinstance(index, Mapping) or index.get("schema") != CAPABILITY_DISCOVERY_INDEX_SCHEMA:
        raise CoreBindingError("CAPABILITY_DISCOVERY_INDEX_INVALID")
    capabilities = index.get("capabilities")
    if not isinstance(capabilities, list):
        raise CoreBindingError("CAPABILITY_DISCOVERY_INDEX_INVALID")
    ids: set[str] = set()
    for capability in capabilities:
        if not isinstance(capability, Mapping) or not isinstance(capability.get("id"), str):
            raise CoreBindingError("CAPABILITY_DISCOVERY_INDEX_INVALID")
        ids.add(capability["id"])
    return ids


def _evidence_layers(evidence: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    layers: dict[str, list[str]] = {}
    for layer in ("architecture", "source", "history", "runtime"):
        refs = evidence.get(layer)
        if (
            not isinstance(refs, (list, tuple))
            or not refs
            or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
        ):
            raise CoreBindingError("CAPABILITY_DISCOVERY_EVIDENCE_REQUIRED")
        layers[layer] = [ref.strip() for ref in refs]
    return layers


def build_capability_discovery_receipt(
    *,
    repository: str,
    main_sha: str,
    index_bytes: bytes | None,
    intent: str,
    disposition: str,
    matched_capability_ids: Sequence[str] | None,
    justification: str = "",
    evidence: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Build a ``nexus.capability_discovery_receipt.v1`` from owner-authored fields.

    The disposition and matched ids are never inferred; they must come from the
    Task Card and the ids must exist in the index at ``main_sha``.
    """
    if not _SHA1_RE.fullmatch(str(main_sha or "")):
        raise CoreBindingError("CAPABILITY_DISCOVERY_REVISION_INVALID")
    known_ids = _load_capability_index(index_bytes)
    assert index_bytes is not None
    chosen = str(disposition or "").strip()
    if not chosen:
        raise CoreBindingError("CAPABILITY_DISPOSITION_REQUIRED")
    if chosen not in CAPABILITY_DISPOSITIONS:
        raise CoreBindingError("CAPABILITY_DISPOSITION_INVALID")
    if chosen not in MUTATING_CAPABILITY_DISPOSITIONS:
        raise CoreBindingError("CAPABILITY_DISPOSITION_BLOCKS_MUTATION")
    if matched_capability_ids is None:
        raise CoreBindingError("CAPABILITY_IDS_REQUIRED")
    ids = [str(item).strip() for item in matched_capability_ids]
    if any(not _CAPABILITY_ID_RE.fullmatch(item) for item in ids) or len(set(ids)) != len(ids):
        raise CoreBindingError("CAPABILITY_IDS_INVALID")
    unknown = [item for item in ids if item not in known_ids]
    if unknown:
        raise CoreBindingError("CAPABILITY_IDS_NOT_IN_INDEX")
    if chosen in DONOR_CAPABILITY_DISPOSITIONS and not ids:
        raise CoreBindingError("CAPABILITY_IDS_REQUIRED")
    reason = str(justification or "").strip()
    if chosen == "NEW_CAPABILITY_JUSTIFIED":
        if ids:
            raise CoreBindingError("CAPABILITY_NEW_MUST_NOT_CLAIM_DONOR")
        if not reason:
            raise CoreBindingError("CAPABILITY_JUSTIFICATION_REQUIRED")
    intent_text = str(intent or "").strip()
    if not intent_text:
        raise CoreBindingError("CAPABILITY_DISCOVERY_INTENT_REQUIRED")
    receipt: dict[str, Any] = {
        "schema": CAPABILITY_DISCOVERY_RECEIPT_SCHEMA,
        "repository": str(repository),
        "indexRevision": str(main_sha),
        "indexPath": CAPABILITY_DISCOVERY_INDEX_PATH,
        "indexSha256": _sha256_bytes(index_bytes),
        "intent": intent_text,
        "disposition": chosen,
        "matchedCapabilityIds": ids,
        "evidence": _evidence_layers(evidence),
    }
    if chosen == "NEW_CAPABILITY_JUSTIFIED":
        receipt["newCapabilityJustification"] = reason
    return receipt


def build_integration_authority(
    inputs: CoreAuthorityInputs, *, operating_mode_sha256: str
) -> dict[str, str]:
    lane = _require_lane(inputs.execution_lane)
    if not _SHA256_RE.fullmatch(str(operating_mode_sha256 or "")):
        raise CoreBindingError("CORE_OPERATING_MODE_MISSING")
    authority_ref = (
        f"github://{inputs.repository}/issues/{inputs.issue_number}@{inputs.revision}"
        f"#task_card:{inputs.task_card_ref}@{inputs.task_card_hash[:16]}"
    )
    authority_hash = core_hash([
        INTEGRATION_AUTHORITY_DOMAIN,
        inputs.repository,
        inputs.issue_number,
        inputs.revision,
        inputs.issue_contract_sha256,
        inputs.item_identity_hash,
        inputs.task_card_ref,
        inputs.task_card_hash,
        inputs.main_sha,
        lane,
        operating_mode_sha256,
        inputs.worker_binding_sha256,
    ])
    return {
        "execution_lane": lane,
        "authority_ref": authority_ref,
        "authority_hash": authority_hash,
    }


def _normalize_paths(paths: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for raw in paths:
        text = str(raw or "").strip()
        path = PurePosixPath(text)
        if not text or path.is_absolute() or ".." in path.parts or "\\" in text or "\x00" in text:
            raise CoreBindingError("CORE_ALLOWED_PATHS_INVALID")
        normalized.append(path.as_posix())
    if not normalized or len(set(normalized)) != len(normalized):
        raise CoreBindingError("CORE_ALLOWED_PATHS_INVALID")
    return normalized


def build_acceptance_contract(
    inputs: CoreAuthorityInputs,
    *,
    unit_id: str,
    mutation_paths: Sequence[str],
    allow_deletions: bool,
) -> tuple[dict[str, Any], str]:
    """Return ``(acceptance_contract, acceptance_contract_hash)`` for one execution unit."""
    if allow_deletions:
        # The Open SWE repair surface has no deletion tool; ALLOW would overstate scope.
        raise CoreBindingError("CORE_DELETION_POLICY_FORBID_REQUIRED")
    if unit_id not in inputs.unit_verifiers:
        raise CoreBindingError("CORE_UNIT_VERIFIERS_MISSING")
    rows = [*inputs.unit_verifiers[unit_id], *inputs.whole_verifiers]
    verifier_ids = [row[0] for row in rows]
    if not verifier_ids:
        raise CoreBindingError("CORE_VERIFIER_IDS_REQUIRED")
    if len(set(verifier_ids)) != len(verifier_ids):
        raise CoreBindingError("CORE_VERIFIER_IDS_DUPLICATE")
    paths = _normalize_paths(mutation_paths)
    requirements_hash = core_hash([
        ACCEPTANCE_REQUIREMENTS_DOMAIN,
        inputs.task_card_hash,
        inputs.issue_contract_sha256,
        unit_id,
        sorted(paths),
        [[row[0], list(row[1]), row[2]] for row in rows],
    ])
    contract = {
        "contract_id": (
            f"eia/{inputs.repository}/issues/{inputs.issue_number}/{inputs.revision}"
            f"/{inputs.task_id}/{unit_id}"
        ),
        "requirements_hash": requirements_hash,
        "required_verifier_ids": verifier_ids,
        "allowed_paths": paths,
        "deletion_policy": DELETION_POLICY,
    }
    return contract, acceptance_contract_hash(contract)


def _rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        raise CoreBindingError("CORE_FRESHNESS_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def binding_id_for(operation_id: str, attempt_id: str) -> str:
    material = core_canonical_json({"operation_id": operation_id, "attempt_id": attempt_id})
    return "eiab_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def workspace_identity(workspace_path: str | Path) -> str:
    resolved = str(Path(workspace_path).expanduser().resolve())
    return "sha256:" + hashlib.sha256(resolved.encode("utf-8")).hexdigest()


def binding_hash_for(binding: Mapping[str, Any]) -> str:
    material = dict(binding)
    material.pop("binding_hash", None)
    return core_hash(material)


def build_repository_mutation_binding(
    *,
    operation_id: str,
    attempt_id: str,
    repository: str,
    origin: str,
    source_revision: str,
    source_tree: str,
    workspace_path: str | Path,
    integration_authority: Mapping[str, str],
    capability_receipt_hash: str,
    index_revision: str,
    acceptance_contract: Mapping[str, Any],
    contract_hash: str,
    created_at: datetime,
    valid_for_seconds: float,
) -> dict[str, Any]:
    if not _SHA256_RE.fullmatch(str(operation_id or "")):
        raise CoreBindingError("CORE_BINDING_OPERATION_INVALID")
    if not str(attempt_id or "").strip():
        raise CoreBindingError("CORE_BINDING_ATTEMPT_INVALID")
    if not _SHA1_RE.fullmatch(str(source_revision or "")) or not _SHA1_RE.fullmatch(
        str(source_tree or "")
    ):
        raise CoreBindingError("CORE_BINDING_SOURCE_INVALID")
    if not _SHA1_RE.fullmatch(str(index_revision or "")):
        raise CoreBindingError("CORE_BINDING_DISCOVERY_INVALID")
    if not _PREFIXED_SHA256_RE.fullmatch(str(capability_receipt_hash or "")):
        raise CoreBindingError("CORE_BINDING_DISCOVERY_INVALID")
    if valid_for_seconds <= 0:
        raise CoreBindingError("CORE_FRESHNESS_WINDOW_INVALID")
    binding: dict[str, Any] = {
        "schema": CORE_MUTATION_BINDING_SCHEMA,
        "binding_id": binding_id_for(operation_id, attempt_id),
        "operation_id": operation_id,
        "attempt_id": attempt_id,
        "repository": {
            "canonical_id": repository,
            "origin": origin,
            "source_revision": f"git-commit:{source_revision}",
            "source_tree": f"git-tree:{source_tree}",
            "workspace_identity": workspace_identity(workspace_path),
            "workspace_mode": WORKSPACE_MODE,
        },
        "integration_authority": dict(integration_authority),
        "capability_discovery": {
            "required": True,
            "receipt_hash": capability_receipt_hash,
            "index_revision": f"git-commit:{index_revision}",
        },
        "core": {
            "protocol_version": CORE_PROTOCOL_VERSION,
            "acceptance_contract": dict(acceptance_contract),
            "acceptance_contract_hash": contract_hash,
        },
        "freshness": {
            "created_at": _rfc3339(created_at),
            "valid_until": _rfc3339(created_at + timedelta(seconds=float(valid_for_seconds))),
            "revalidate_before_first_effect": True,
        },
    }
    binding["binding_hash"] = binding_hash_for(binding)
    return binding


def unit_verifier_cycle_seconds(inputs: CoreAuthorityInputs, unit_id: str) -> float:
    """Upper bound of one closure verification cycle for ``unit_id``.

    Sum of that unit's verifier timeouts plus every whole-task verifier timeout,
    taken from the same Core authority inputs that pin the acceptance contract.
    """
    if unit_id not in inputs.unit_verifiers:
        raise CoreBindingError("CORE_UNIT_VERIFIERS_MISSING")
    rows = [*inputs.unit_verifiers[unit_id], *inputs.whole_verifiers]
    return float(sum(float(row[2]) for row in rows))


def unit_closure_cycle_seconds(inputs: CoreAuthorityInputs, unit_id: str) -> float:
    """Upper bound of one full closure cycle for ``unit_id``.

    The contract verifier timeouts (``unit_verifier_cycle_seconds``) plus closure's
    built-in integrity checks, which run with their own git timeout at unit and
    whole-task scope and are not part of the acceptance contract.
    """
    return unit_verifier_cycle_seconds(inputs, unit_id) + CLOSURE_INTEGRITY_CYCLE_SECONDS


def binding_validity_seconds(
    worker_timeout_seconds: float,
    max_repairs_per_unit: int,
    verifier_cycle_seconds: float = 0.0,
) -> float:
    """Freshness window covering the initial bound run plus every budgeted repair run.

    The binding must stay valid for the whole bounded repair lifecycle of one unit:
    one initial worker run and at most ``max_repairs_per_unit`` same-session repair
    continuations, each bounded by the worker timeout and each followed by one
    closure verification cycle (``verifier_cycle_seconds``: the unit's verifier
    timeouts plus the whole-task verifier timeouts), plus a fixed margin.  Pure.
    """
    if (
        isinstance(max_repairs_per_unit, bool)
        or not isinstance(max_repairs_per_unit, int)
        or not 0 <= max_repairs_per_unit <= MAX_REPAIRS_PER_UNIT_LIMIT
    ):
        raise CoreBindingError("CORE_REPAIR_BUDGET_INVALID")
    timeout = float(worker_timeout_seconds)
    if timeout <= 0:
        raise CoreBindingError("CORE_FRESHNESS_WINDOW_INVALID")
    if isinstance(verifier_cycle_seconds, bool):
        raise CoreBindingError("CORE_VERIFIER_WINDOW_INVALID")
    verifier = float(verifier_cycle_seconds)
    if not math.isfinite(verifier) or verifier < 0:
        raise CoreBindingError("CORE_VERIFIER_WINDOW_INVALID")
    return (timeout + verifier) * (1 + max_repairs_per_unit) + FRESHNESS_MARGIN_SECONDS


def bound_operation_material(
    *,
    operation: str,
    workspace_path: str | Path,
    attempt_id: str,
    unit_identity_sha256: str,
    semantic_envelope_sha256: str,
    worker_identity_sha256: str,
) -> dict[str, str]:
    """Binding-free operation identity material for a bound dispatch.

    The legacy formula hashes the prompt/artifact, which now contain the binding that
    itself pins ``operation_id``; that would be circular.
    """
    return {
        "schema": BOUND_OPERATION_SCHEMA,
        "operation": operation,
        "workspace": str(Path(workspace_path).expanduser().resolve()),
        "attempt_id": attempt_id,
        "unit_identity_sha256": unit_identity_sha256,
        "semantic_envelope_sha256": semantic_envelope_sha256,
        "session_id": "",
        "worker_identity_sha256": worker_identity_sha256,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _canonical_binding_repository(value: str) -> str:
    match = re.fullmatch(r"([^/\s]+)/([^/\s]+)", str(value or "").strip())
    return f"{match.group(1)}/{match.group(2)}".lower() if match else ""


def canonical_origin_repository(value: str) -> str:
    text = str(value or "").strip()
    patterns = (
        r"^https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
        r"^git@github\.com:([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
        r"^ssh://git@github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}/{match.group(2)}".lower()
    return ""


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _prefixed(value: Any) -> bool:
    return isinstance(value, str) and _PREFIXED_SHA256_RE.fullmatch(value) is not None


def validate_binding_structure(binding: Any) -> None:
    """Structural/self-hash validation that needs no workspace observation."""
    if not isinstance(binding, Mapping) or set(binding) != _BINDING_KEYS:
        raise CoreBindingError("core_binding_shape")
    repository = binding.get("repository")
    authority = binding.get("integration_authority")
    discovery = binding.get("capability_discovery")
    core = binding.get("core")
    freshness = binding.get("freshness")
    if (
        not isinstance(repository, Mapping)
        or set(repository) != _REPOSITORY_KEYS
        or not isinstance(authority, Mapping)
        or set(authority) != _AUTHORITY_KEYS
        or not isinstance(discovery, Mapping)
        or set(discovery) != _DISCOVERY_KEYS
        or not isinstance(core, Mapping)
        or set(core) != _CORE_KEYS
        or not isinstance(freshness, Mapping)
        or set(freshness) != _FRESHNESS_KEYS
    ):
        raise CoreBindingError("core_binding_shape")
    if binding.get("schema") != CORE_MUTATION_BINDING_SCHEMA:
        raise CoreBindingError("core_binding_schema")
    if not isinstance(binding.get("binding_id"), str) or not binding["binding_id"].strip():
        raise CoreBindingError("core_binding_identity")
    if not _prefixed(binding.get("binding_hash")) or (
        binding_hash_for(binding) != binding["binding_hash"]
    ):
        raise CoreBindingError("core_binding_hash")
    contract = core.get("acceptance_contract")
    if (
        core.get("protocol_version") != CORE_PROTOCOL_VERSION
        or not isinstance(contract, Mapping)
        or set(contract) != _ACCEPTANCE_KEYS
    ):
        raise CoreBindingError("core_binding_contract")
    if (
        not isinstance(contract.get("contract_id"), str)
        or not contract["contract_id"].strip()
        or not _prefixed(contract.get("requirements_hash"))
        or not _string_list(contract.get("required_verifier_ids"))
        or not contract["required_verifier_ids"]
        or len(set(contract["required_verifier_ids"])) != len(contract["required_verifier_ids"])
        or not _string_list(contract.get("allowed_paths"))
        or not contract["allowed_paths"]
        or len(set(contract["allowed_paths"])) != len(contract["allowed_paths"])
        or contract.get("deletion_policy") not in {"FORBID", "ALLOW"}
    ):
        raise CoreBindingError("core_binding_contract")
    if contract.get("deletion_policy") != DELETION_POLICY:
        raise CoreBindingError("core_binding_deletion")
    if not _prefixed(core.get("acceptance_contract_hash")) or (
        _mirror_acceptance_contract_hash(contract) != core["acceptance_contract_hash"]
    ):
        raise CoreBindingError("core_binding_contract_hash")


def validate_repository_mutation_binding(
    binding: Any,
    *,
    operation_id: str,
    attempt_id: str,
    repository: str,
    expected_base: str,
    observed_origin: str,
    observed_base_tree: str,
    workspace_path: str | Path,
    allowed_paths: Sequence[str],
    now: datetime | None = None,
    continuation: bool = False,
) -> None:
    """Mirror runtime ``_validate_repository_mutation_binding`` for pre-effect revalidation.

    Raises ``CoreBindingError`` with the runtime's reason code.

    ``continuation=True`` revalidates the binding of an already BOUND session before a
    repair continuation.  ``valid_until`` still bounds the whole bounded repair
    lifecycle (it is minted to cover the initial run plus every budgeted repair), so a
    continuation additionally requires a deadline to exist and ``created_at`` not to
    lie in the future, mirroring the runtime's continuation admission.
    """
    validate_binding_structure(binding)
    assert isinstance(binding, Mapping)
    if binding.get("operation_id") != operation_id:
        raise CoreBindingError("core_binding_operation")
    bound_attempt = binding.get("attempt_id")
    if not isinstance(bound_attempt, str) or not bound_attempt.strip():
        raise CoreBindingError("core_binding_operation")
    if attempt_id not in (None, "") and attempt_id != bound_attempt:
        raise CoreBindingError("core_binding_operation")
    repo = binding["repository"]
    canonical_id = repo.get("canonical_id")
    origin = repo.get("origin")
    if (
        not isinstance(canonical_id, str)
        or _canonical_binding_repository(canonical_id) != _canonical_binding_repository(repository)
        or not _canonical_binding_repository(repository)
        or not isinstance(origin, str)
        or canonical_origin_repository(origin) != canonical_origin_repository(observed_origin)
        or not canonical_origin_repository(observed_origin)
    ):
        raise CoreBindingError("core_binding_repository")
    if repo.get("source_revision") != f"git-commit:{expected_base}" or not (
        isinstance(repo.get("source_tree"), str) and _GIT_TREE_RE.fullmatch(repo["source_tree"])
    ):
        raise CoreBindingError("core_binding_source")
    if repo["source_tree"] != f"git-tree:{observed_base_tree}":
        raise CoreBindingError("core_binding_source")
    if repo.get("workspace_identity") != workspace_identity(workspace_path) or repo.get(
        "workspace_mode"
    ) not in {"checkout", "managed_worktree", "target"}:
        raise CoreBindingError("core_binding_workspace")
    authority = binding["integration_authority"]
    if authority.get("execution_lane") not in EXECUTION_LANES:
        raise CoreBindingError("core_binding_authority")
    if (
        not isinstance(authority.get("authority_ref"), str)
        or not authority["authority_ref"].strip()
        or not _prefixed(authority.get("authority_hash"))
    ):
        raise CoreBindingError("core_binding_authority")
    discovery = binding["capability_discovery"]
    if (
        discovery.get("required") is not True
        or not _prefixed(discovery.get("receipt_hash"))
        or not (
            isinstance(discovery.get("index_revision"), str)
            and _GIT_COMMIT_RE.fullmatch(discovery["index_revision"])
        )
    ):
        raise CoreBindingError("core_binding_discovery")
    contract = binding["core"]["acceptance_contract"]
    try:
        contract_paths = _normalize_paths(contract["allowed_paths"])
        expected_paths = _normalize_paths(list(allowed_paths))
    except CoreBindingError as exc:
        raise CoreBindingError("core_binding_scope") from exc
    if sorted(contract_paths) != sorted(expected_paths):
        raise CoreBindingError("core_binding_scope")
    freshness = binding["freshness"]
    if freshness.get("revalidate_before_first_effect") is not True:
        raise CoreBindingError("core_binding_freshness")
    created_at = _parse_rfc3339(freshness.get("created_at"))
    if created_at is None:
        raise CoreBindingError("core_binding_freshness")
    current = now or datetime.now(timezone.utc)
    valid_until = freshness.get("valid_until")
    deadline = _parse_rfc3339(valid_until) if valid_until is not None else None
    if valid_until is not None and deadline is None:
        raise CoreBindingError("core_binding_freshness")
    if continuation and (deadline is None or created_at > current):
        raise CoreBindingError("core_binding_freshness")
    if deadline is not None and deadline <= current:
        raise CoreBindingError("core_binding_freshness")


# ---------------------------------------------------------------------------
# Envelope derivation
# ---------------------------------------------------------------------------


def derive_bound_envelope(
    semantic_envelope: Mapping[str, Any], binding: Mapping[str, Any]
) -> dict[str, Any]:
    """Return ``semantic ∪ {repository_mutation_binding}`` without mutating the input."""
    if semantic_envelope.get("schema") != ENVELOPE_SCHEMA_V2:
        raise CoreBindingError("CORE_BINDING_REQUIRES_V2_ENVELOPE")
    if BINDING_KEY in semantic_envelope:
        raise CoreBindingError("CORE_BINDING_SEMANTIC_ENVELOPE_ALREADY_BOUND")
    validate_binding_structure(binding)
    bound = dict(semantic_envelope)
    bound[BINDING_KEY] = dict(binding)
    return bound


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def parse_bound_execution_envelope_v2(
    text: str, *, semantic_envelope_sha256: str
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Parse a bound v2 envelope.

    Returns ``(semantic_envelope, binding, bound_envelope_sha256)``.  The remainder
    after stripping the binding must be a valid semantic v2 envelope whose envelope
    canonical digest equals ``semantic_envelope_sha256``.
    """
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
    except (TypeError, ValueError) as exc:
        raise CoreBindingError("CORE_BOUND_ENVELOPE_PARSE_FAILED") from exc
    if not isinstance(value, dict) or value.get("schema") != ENVELOPE_SCHEMA_V2:
        raise CoreBindingError("CORE_BOUND_ENVELOPE_SCHEMA_INVALID")
    if BINDING_KEY not in value:
        raise CoreBindingError("CORE_BOUND_ENVELOPE_BINDING_MISSING")
    semantic = dict(value)
    binding = semantic.pop(BINDING_KEY)
    if envelope_sha256(semantic) != str(semantic_envelope_sha256 or "").lower():
        raise CoreBindingError("CORE_BOUND_ENVELOPE_SEMANTIC_MISMATCH")
    try:
        parse_external_execution_envelope_v2(envelope_canonical_json(semantic))
    except ExternalIntelligenceError as exc:
        raise CoreBindingError("CORE_BOUND_ENVELOPE_SEMANTIC_INVALID") from exc
    try:
        validate_binding_structure(binding)
    except CoreBindingError as exc:
        raise CoreBindingError(f"CORE_BOUND_ENVELOPE_BINDING_INVALID:{exc}") from exc
    return semantic, dict(binding), envelope_sha256(value)


__all__ = [
    "BINDING_KEY",
    "BOUND_OPERATION_SCHEMA",
    "CAPABILITY_DISCOVERY_INDEX_PATH",
    "CAPABILITY_DISCOVERY_RECEIPT_SCHEMA",
    "CAPABILITY_DISPOSITIONS",
    "CLOSURE_INTEGRITY_CHECK_COUNT",
    "CLOSURE_INTEGRITY_CYCLE_SECONDS",
    "CLOSURE_INTEGRITY_GIT_TIMEOUT_SECONDS",
    "CLOSURE_INTEGRITY_SCOPES_PER_CYCLE",
    "CORE_MUTATION_BINDING_SCHEMA",
    "CORE_PROTOCOL_VERSION",
    "EXECUTION_LANES",
    "FRESHNESS_MARGIN_SECONDS",
    "MAX_REPAIRS_PER_UNIT_LIMIT",
    "MUTATING_CAPABILITY_DISPOSITIONS",
    "OPERATING_MODE_PATH",
    "CoreAuthorityInputs",
    "CoreBindingError",
    "acceptance_contract_hash",
    "binding_hash_for",
    "binding_validity_seconds",
    "unit_closure_cycle_seconds",
    "unit_verifier_cycle_seconds",
    "binding_id_for",
    "bound_operation_material",
    "build_acceptance_contract",
    "build_capability_discovery_receipt",
    "build_integration_authority",
    "build_repository_mutation_binding",
    "canonical_origin_repository",
    "core_canonical_json",
    "core_hash",
    "derive_bound_envelope",
    "envelope_canonical_json",
    "envelope_sha256",
    "parse_bound_execution_envelope_v2",
    "validate_binding_structure",
    "validate_repository_mutation_binding",
    "workspace_identity",
]
