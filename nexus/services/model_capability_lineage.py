"""Cumulative model-capability lineage registry and calibration planner.

This module implements a machine-readable, schema-bound calibration layer that
keeps three concerns separate:

* semantic model capability lineage (what the model can do);
* exact execution/transport identity (which alias, CLI, adapter, or transport
  was exercised);
* repository admitted authority (WorkforcePolicyLoader / model_workforce.yaml).

It is calibration evidence and planning ONLY.  It must never become Workforce
Admission authority: it cannot admit a worker, select a route, promote
autonomy, or call a provider.  The three-arm benchmark
(``scripts/bench/experimental/model_workforce_three_arm.py``) remains the
baseline/comparative diagnostic instrument; the cumulative requalification
path implemented here reuses still-valid lower-tier semantic evidence instead
of restarting from L1.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

import yaml

from nexus.services.model_workforce_policy import WorkforcePolicyLoader

# Tier ordering used only for calibration planning.  It intentionally mirrors
# the workforce autonomy ranks and extends them to L4 so the experimental
# ceiling is representable without changing workforce admission semantics.
LINEAGE_TIERS: tuple[str, ...] = ("L0", "L0.25", "L0.5", "L1", "L2", "L3", "L4")

CALIBRATION_PLAN_SCHEMA = "nexus.model_calibration_plan.v1"
CALIBRATION_EVIDENCE_SCHEMA = "nexus.model_calibration_evidence.v1"
REGISTRY_SCHEMA = "nexus.model_capability_lineage.v1"

# Explicitly separate admission authority from calibration evidence.  The plan
# and evidence actions never establish admission; this constant is surfaced in
# every machine-readable payload so a consumer cannot confuse the two.
ADMISSION_AUTHORITY_SEPARATE = "SEPARATE_NOT_ESTABLISHED_BY_THIS_ACTION"
ADMISSION_AUTHORITY_DISCLAIMER = (
    "This is calibration evidence only and is NOT Workforce Admission. "
    "Capability-lineage equivalence never implies admission equivalence. "
    "Workforce admission requires the exact registered execution identity "
    "through WorkforcePolicyLoader semantics."
)

# Stable change-impact classification.  Order is materiality precedence:
# the first matching category wins deterministically.
CHANGE_KIND_VALUES: tuple[str, ...] = (
    "new_lineage",
    "alias_only",
    "transport_only",
    "cli_or_adapter_change",
    "prompt_template_or_thinking_change",
    "model_revision_or_backend_change",
    "unknown_material_change",
)

# Truthfulness statuses for calibration evidence provenance.  Capability
# calibration evidence must never claim a reference it does not have.  A
# record is either bound to a real durable repository receipt, or it is
# explicitly Owner-approved / awaiting durable writeback.  Current workforce
# admission records (model_workforce.yaml) are authority context, never
# capability calibration evidence.
PROVENANCE_OWNER_DECISION = "OWNER_DECISION"
PROVENANCE_EXTERNAL_CALIBRATION_PENDING_WRITEBACK = (
    "EXTERNAL_CALIBRATION_RECEIPT_PENDING_DURABLE_WRITEBACK"
)
PROVENANCE_WORKFORCE_AUTHORITY_REF = "WORKFORCE_AUTHORITY_REF"
PROVENANCE_DURABLE_RECEIPT = "DURABLE_REPOSITORY_RECEIPT"
PROVENANCE_VALUES: tuple[str, ...] = (
    PROVENANCE_OWNER_DECISION,
    PROVENANCE_EXTERNAL_CALIBRATION_PENDING_WRITEBACK,
    PROVENANCE_WORKFORCE_AUTHORITY_REF,
    PROVENANCE_DURABLE_RECEIPT,
)

# model_workforce.yaml is machine-checkable provenance.  Capability evidence
# refs into this file must resolve to a worker whose provider+model matches an
# execution identity of the same lineage; otherwise the record is rejected as
# contradictory provenance.
WORKFORCE_AUTHORITY_PATH_MARKER = "nexus/config/model_workforce.yaml"


class ChangeClass(str, Enum):
    """Deterministic change-impact classes for a requalification request."""

    NEW_LINEAGE = "NEW_LINEAGE"
    ALIAS_ONLY = "ALIAS_ONLY"
    TRANSPORT_ONLY = "TRANSPORT_ONLY"
    CLI_OR_ADAPTER_CHANGE = "CLI_OR_ADAPTER_CHANGE"
    PROMPT_TEMPLATE_OR_THINKING_CHANGE = "PROMPT_TEMPLATE_OR_THINKING_CHANGE"
    MODEL_REVISION_OR_BACKEND_CHANGE = "MODEL_REVISION_OR_BACKEND_CHANGE"
    UNKNOWN_MATERIAL_CHANGE = "UNKNOWN_MATERIAL_CHANGE"


class EvidencePhase(str, Enum):
    """Evidence phases that must never be collapsed into one status."""

    FIRST_PASS = "FIRST_PASS"
    INDEPENDENT_HIDDEN_PROBE = "INDEPENDENT_HIDDEN_PROBE"
    VERIFIER_GUIDED_REPAIR = "VERIFIER_GUIDED_REPAIR"


class EvidenceScope(str, Enum):
    """Whether an evidence record binds semantic capability or execution identity."""

    SEMANTIC = "SEMANTIC"
    IDENTITY_OR_TRANSPORT = "IDENTITY_OR_TRANSPORT"


class TrialKind(str, Enum):
    """Kinds of trials a calibration plan can require."""

    FULL_BASELINE = "FULL_BASELINE"
    IDENTITY_RESOLUTION = "IDENTITY_RESOLUTION"
    TRANSPORT_PREFLIGHT = "TRANSPORT_PREFLIGHT"
    PROTOCOL_TOOL_ISOLATION = "PROTOCOL_TOOL_ISOLATION"
    STABLE_FLOOR_REGRESSION = "STABLE_FLOOR_REGRESSION"
    FRONTIER_EVALUATION = "FRONTIER_EVALUATION"
    FRONTIER_HIDDEN_PROBE = "FRONTIER_HIDDEN_PROBE"
    VERIFIER_GUIDED_REPAIR = "VERIFIER_GUIDED_REPAIR"
    FRONTIER_PLUS_ONE_EXPLORATORY = "FRONTIER_PLUS_ONE_EXPLORATORY"


class LineageError(Exception):
    """Base exception for lineage registry and calibration planner errors."""


class LineageValidationError(LineageError):
    """Raised when the lineage registry file fails schema or semantic validation."""


class LineageResolutionError(LineageError):
    """Raised when a lineage lookup is unknown, ambiguous, or incomplete."""


def parse_lineage_tier(tier: str | None) -> int:
    """Parse a calibration tier into a deterministic rank.

    Raises ValueError for unrecognized tiers.
    """
    if tier is None:
        raise ValueError("tier is required")
    clean = str(tier).strip()
    if clean not in LINEAGE_TIERS:
        raise ValueError(f"Unknown calibration tier: {tier}")
    return LINEAGE_TIERS.index(clean)


def tiers_strictly_below(tier: str | None) -> tuple[str, ...]:
    """Return all calibration tiers strictly below ``tier``."""
    rank = parse_lineage_tier(tier)
    return LINEAGE_TIERS[:rank]


def next_lineage_tier(tier: str | None) -> str | None:
    """Return the next higher calibration tier, or None at the ceiling."""
    rank = parse_lineage_tier(tier)
    if rank + 1 >= len(LINEAGE_TIERS):
        return None
    return LINEAGE_TIERS[rank + 1]


def frontier_plus_one_trials(frontier: str) -> tuple[CalibrationTrial, ...]:
    """Optional exploratory probe at frontier+1.

    The trial tier MUST equal the next formal tier (e.g. frontier L3 -> L4).
    When the frontier is already the highest formal tier (L4) no L5 is
    fabricated: the trial is simply omitted.
    """
    next_tier = next_lineage_tier(frontier)
    if next_tier is None:
        return ()
    return (
        CalibrationTrial(
            tier=next_tier,
            kind=TrialKind.FRONTIER_PLUS_ONE_EXPLORATORY,
            reason=f"optional exploratory probe at {next_tier}",
            optional=True,
        ),
    )


@dataclass(frozen=True)
class ExecutionIdentity:
    """One exact registered execution identity / alias of a lineage."""

    provider: str
    model: str
    identity_kind: str = "primary"
    transport: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "model": self.model,
            "identity_kind": self.identity_kind,
            "transport": self.transport,
        }


@dataclass(frozen=True)
class EvidenceRef:
    """A schema-bound reference to calibration evidence.

    ``provenance`` is the truthfulness status of the reference.  Capability
    calibration evidence must never claim a reference it does not have; when
    no durable repository receipt exists the record is Owner-approved with an
    explicit provenance status (e.g. OWNER_DECISION or
    EXTERNAL_CALIBRATION_RECEIPT_PENDING_DURABLE_WRITEBACK) instead of
    pointing at an unrelated workforce authority record.
    """

    ref: str
    phase: EvidencePhase
    tier: str | None = None
    scope: EvidenceScope = EvidenceScope.SEMANTIC
    date: str | None = None
    digest: str | None = None
    provenance: str = ""

    def to_dict(self) -> dict[str, str | None]:
        return {
            "ref": self.ref,
            "phase": self.phase.value,
            "tier": self.tier,
            "scope": self.scope.value,
            "date": self.date,
            "digest": self.digest,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class LineageEvidence:
    """A concrete evidence record for a lineage.

    ``phase`` is immutable: a VERIFIER_GUIDED_REPAIR pass never rewrites a
    FIRST_PASS record's status.  ``provenance`` separates capability
    calibration evidence from current workforce admission authority.
    """

    id: str
    phase: EvidencePhase
    status: str
    tier: str | None = None
    scope: EvidenceScope = EvidenceScope.SEMANTIC
    date: str | None = None
    digest: str | None = None
    provenance: str = ""
    score: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "id": self.id,
            "phase": self.phase.value,
            "status": self.status,
            "tier": self.tier,
            "scope": self.scope.value,
            "date": self.date,
            "digest": self.digest,
            "provenance": self.provenance,
            "score": self.score,
            "note": self.note,
        }


@dataclass(frozen=True)
class WorkforceAuthorityRef:
    """Current workforce admission authority context, never capability evidence.

    These references document what model_workforce.yaml currently admits for a
    lineage.  They are intentionally kept separate from capability calibration
    evidence and carry no calibration weight.
    """

    ref: str
    provider: str
    model: str
    current_autonomy: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "ref": self.ref,
            "provider": self.provider,
            "model": self.model,
            "current_autonomy": self.current_autonomy,
            "note": self.note,
        }


@dataclass(frozen=True)
class KnownFailureFamily:
    """A known failure family whose adjacent variants remain queryable."""

    family: str
    ref: str = ""
    status: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"family": self.family, "ref": self.ref, "status": self.status}


@dataclass(frozen=True)
class CapabilityLineage:
    """One semantic capability lineage (calibration evidence only)."""

    lineage_id: str
    canonical_family: str
    execution_identities: tuple[ExecutionIdentity, ...]
    stable_floor: str
    current_frontier: str
    conditional_ceiling: str
    experimental_ceiling: str
    frontier_experimental: bool = False
    description: str = ""
    experimental_notes: tuple[str, ...] = ()
    role_evidence: tuple[EvidenceRef, ...] = ()
    known_failure_families: tuple[KnownFailureFamily, ...] = ()
    evidence: tuple[LineageEvidence, ...] = ()
    workforce_authority_refs: tuple[WorkforceAuthorityRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "lineage_id": self.lineage_id,
            "canonical_family": self.canonical_family,
            "description": self.description,
            "execution_identities": [identity.to_dict() for identity in self.execution_identities],
            "stable_floor": self.stable_floor,
            "current_frontier": self.current_frontier,
            "frontier_experimental": self.frontier_experimental,
            "conditional_ceiling": self.conditional_ceiling,
            "experimental_ceiling": self.experimental_ceiling,
            "experimental_notes": list(self.experimental_notes),
            "role_evidence": [ref.to_dict() for ref in self.role_evidence],
            "known_failure_families": [family.to_dict() for family in self.known_failure_families],
            "evidence": [record.to_dict() for record in self.evidence],
            "workforce_authority_refs": [ref.to_dict() for ref in self.workforce_authority_refs],
            "admission_authority": ADMISSION_AUTHORITY_DISCLAIMER,
        }


@dataclass(frozen=True)
class ChangeDeclaration:
    """Structured, machine-readable declaration of a requalification change."""

    provider: str = ""
    model: str = ""
    new_lineage: bool = False
    alias_only: bool = False
    transport_change: bool = False
    cli_or_adapter_change: bool = False
    prompt_template_change: bool = False
    thinking_change: bool = False
    model_revision_change: bool = False
    backend_change: bool = False
    description: str = ""


@dataclass(frozen=True)
class CalibrationTrial:
    """One required trial in a calibration plan."""

    tier: str
    kind: TrialKind
    reason: str
    phase: EvidencePhase | None = None
    optional: bool = False
    failure_family: str | None = None
    hidden_case: str = "fresh"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "kind": self.kind.value,
            "reason": self.reason,
            "phase": self.phase.value if self.phase else None,
            "optional": self.optional,
            "failure_family": self.failure_family,
            "hidden_case": self.hidden_case,
        }


@dataclass(frozen=True)
class NotRequiredTrial:
    """A lower suite explicitly excluded from a requalification plan."""

    tier: str
    suite: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"tier": self.tier, "suite": self.suite, "reason": self.reason}


@dataclass(frozen=True)
class CalibrationPlan:
    """A cumulative minimum-requalification plan for one model lineage."""

    schema: str = CALIBRATION_PLAN_SCHEMA
    lineage_id: str = ""
    canonical_family: str = ""
    provider: str = ""
    model: str = ""
    target_role: str = ""
    stable_floor: str | None = None
    current_frontier: str | None = None
    frontier_experimental: bool = False
    change_class: ChangeClass = ChangeClass.UNKNOWN_MATERIAL_CHANGE
    plan_status: str = "PLANNED"
    reusable_evidence: tuple[Mapping[str, Any], ...] = ()
    invalidated_evidence: tuple[Mapping[str, Any], ...] = ()
    required_trials: tuple[CalibrationTrial, ...] = ()
    not_required_trials: tuple[NotRequiredTrial, ...] = ()
    failure_family_probes: tuple[Mapping[str, str], ...] = ()
    reasons: tuple[str, ...] = ()
    admission_authority: str = ADMISSION_AUTHORITY_SEPARATE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "lineage_id": self.lineage_id,
            "canonical_family": self.canonical_family,
            "provider": self.provider,
            "model": self.model,
            "target_role": self.target_role,
            "stable_floor": self.stable_floor,
            "current_frontier": self.current_frontier,
            "frontier_experimental": self.frontier_experimental,
            "change_class": self.change_class.value,
            "plan_status": self.plan_status,
            "reusable_evidence": [dict(entry) for entry in self.reusable_evidence],
            "invalidated_evidence": [dict(entry) for entry in self.invalidated_evidence],
            "required_trials": [trial.to_dict() for trial in self.required_trials],
            "not_required_trials": [trial.to_dict() for trial in self.not_required_trials],
            "failure_family_probes": [dict(entry) for entry in self.failure_family_probes],
            "reasons": list(self.reasons),
            "admission_authority": self.admission_authority,
        }


def _parse_phase(value: Any) -> EvidencePhase:
    try:
        return EvidencePhase(str(value).strip().upper())
    except ValueError as exc:
        raise LineageValidationError(f"Invalid evidence phase: {value}") from exc


def _parse_scope(value: Any) -> EvidenceScope:
    try:
        return EvidenceScope(str(value).strip().upper())
    except ValueError as exc:
        raise LineageValidationError(f"Invalid evidence scope: {value}") from exc


def _require_tier(value: Any, context: str) -> str:
    tier = str(value or "").strip()
    try:
        parse_lineage_tier(tier)
    except ValueError as exc:
        raise LineageValidationError(f"{context}: invalid tier {value!r}") from exc
    return tier


def _resolve_worker_from_ref(ref: str, workers: Mapping[str, Any]) -> Any | None:
    """Resolve a model_workforce.yaml ref anchor like #workers.<worker_id>."""
    if "#workers." not in ref:
        return None
    anchor = ref.split("#", 1)[1]
    if not anchor.startswith("workers."):
        return None
    parts = anchor.split(".")
    worker_id = parts[1] if len(parts) > 1 else ""
    return workers.get(worker_id)


class ModelCapabilityLineageRegistry:
    """Fail-closed loader and read-only query surface for capability lineages.

    This registry is calibration evidence only and is never Workforce Admission
    authority.  Identity resolution is exact-match only: no fuzzy name matching,
    and identical marketing text never implies registry membership.
    """

    DEFAULT_LINEAGE_PATH = (
        Path(__file__).resolve().parents[2] / "nexus/config/model_capability_lineage.yaml"
    )

    def __init__(
        self,
        lineage_path: str | Path | None = None,
        workforce_loader: WorkforcePolicyLoader | None = None,
    ) -> None:
        if lineage_path is None:
            self.lineage_path = Path(self.DEFAULT_LINEAGE_PATH)
        else:
            self.lineage_path = Path(lineage_path)
        self._workforce_loader = workforce_loader or WorkforcePolicyLoader()
        self._lineages: dict[str, CapabilityLineage] = {}
        self._identity_index: dict[tuple[str, str], str] = {}
        self._loaded = False

    def _parse_execution_identity(
        self, raw: Mapping[str, Any], lineage_id: str
    ) -> ExecutionIdentity:
        provider = str(raw.get("provider") or "").strip()
        model = str(raw.get("model") or "").strip()
        if not provider or not model:
            raise LineageValidationError(
                f"Lineage '{lineage_id}' has an execution identity missing provider/model"
            )
        return ExecutionIdentity(
            provider=provider,
            model=model,
            identity_kind=str(raw.get("identity_kind") or "primary").strip() or "primary",
            transport=str(raw.get("transport") or "").strip(),
        )

    def _parse_lineage(self, raw: Mapping[str, Any]) -> CapabilityLineage:
        lineage_id = str(raw.get("lineage_id") or "").strip()
        if not lineage_id:
            raise LineageValidationError("A lineage record is missing lineage_id")
        canonical_family = str(raw.get("canonical_family") or "").strip() or lineage_id
        identities_raw = raw.get("execution_identities")
        if not isinstance(identities_raw, list) or not identities_raw:
            raise LineageValidationError(
                f"Lineage '{lineage_id}' must define a non-empty execution_identities list"
            )
        identities = tuple(
            self._parse_execution_identity(entry, lineage_id) for entry in identities_raw
        )

        role_evidence_raw = raw.get("role_evidence") or []
        role_evidence: list[EvidenceRef] = []
        for entry in role_evidence_raw:
            if not isinstance(entry, Mapping):
                raise LineageValidationError(
                    f"Lineage '{lineage_id}' role_evidence entries must be objects"
                )
            role_evidence.append(
                EvidenceRef(
                    ref=str(entry.get("ref") or ""),
                    phase=_parse_phase(entry.get("phase")),
                    tier=str(entry.get("tier") or "").strip() or None,
                    scope=_parse_scope(entry.get("scope")),
                    date=str(entry.get("date") or "").strip() or None,
                    digest=str(entry.get("digest") or "").strip() or None,
                    provenance=str(entry.get("provenance") or "").strip(),
                )
            )

        failure_families_raw = raw.get("known_failure_families") or []
        failure_families = tuple(
            KnownFailureFamily(
                family=str(entry.get("family") or "").strip(),
                ref=str(entry.get("ref") or "").strip(),
                status=str(entry.get("status") or "").strip(),
            )
            for entry in failure_families_raw
            if isinstance(entry, Mapping)
        )

        evidence_raw = raw.get("evidence") or []
        evidence: list[LineageEvidence] = []
        for entry in evidence_raw:
            if not isinstance(entry, Mapping):
                raise LineageValidationError(
                    f"Lineage '{lineage_id}' evidence entries must be objects"
                )
            evidence.append(
                LineageEvidence(
                    id=str(entry.get("id") or "").strip(),
                    phase=_parse_phase(entry.get("phase")),
                    status=str(entry.get("status") or "").strip(),
                    tier=str(entry.get("tier") or "").strip() or None,
                    scope=_parse_scope(entry.get("scope")),
                    date=str(entry.get("date") or "").strip() or None,
                    digest=str(entry.get("digest") or "").strip() or None,
                    provenance=str(entry.get("provenance") or "").strip(),
                    score=str(entry.get("score") or "").strip() or None,
                    note=str(entry.get("note") or "").strip() or None,
                )
            )

        experimental_notes_raw = raw.get("experimental_notes") or []

        workforce_authority_raw = raw.get("workforce_authority_refs") or []
        workforce_authority_refs = tuple(
            WorkforceAuthorityRef(
                ref=str(entry.get("ref") or ""),
                provider=str(entry.get("provider") or ""),
                model=str(entry.get("model") or ""),
                current_autonomy=str(entry.get("current_autonomy") or ""),
                note=str(entry.get("note") or ""),
            )
            for entry in workforce_authority_raw
            if isinstance(entry, Mapping)
        )

        return CapabilityLineage(
            lineage_id=lineage_id,
            canonical_family=canonical_family,
            execution_identities=identities,
            stable_floor=_require_tier(
                raw.get("stable_floor"), f"Lineage '{lineage_id}'.stable_floor"
            ),
            current_frontier=_require_tier(
                raw.get("current_frontier"), f"Lineage '{lineage_id}'.current_frontier"
            ),
            conditional_ceiling=_require_tier(
                raw.get("conditional_ceiling"), f"Lineage '{lineage_id}'.conditional_ceiling"
            ),
            experimental_ceiling=_require_tier(
                raw.get("experimental_ceiling"), f"Lineage '{lineage_id}'.experimental_ceiling"
            ),
            frontier_experimental=bool(raw.get("frontier_experimental", False)),
            description=str(raw.get("description") or "").strip(),
            experimental_notes=tuple(str(n) for n in experimental_notes_raw if isinstance(n, str)),
            role_evidence=tuple(role_evidence),
            known_failure_families=failure_families,
            evidence=tuple(evidence),
            workforce_authority_refs=workforce_authority_refs,
        )

    def load(self) -> dict[str, CapabilityLineage]:
        """Load and validate the lineage registry.

        Raises LineageValidationError when the file is missing, the schema is
        wrong, or the registry is internally inconsistent (duplicate
        lineage_id or duplicate execution identity).
        """
        if not self.lineage_path.is_file():
            raise LineageValidationError(f"Lineage registry file not found: {self.lineage_path}")

        try:
            content = self.lineage_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except Exception as exc:
            raise LineageValidationError(
                f"Failed to parse YAML from {self.lineage_path}: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise LineageValidationError(
                f"Lineage registry content in {self.lineage_path} must be a YAML object"
            )
        if data.get("schema") != REGISTRY_SCHEMA:
            raise LineageValidationError(
                f"Invalid schema: expected '{REGISTRY_SCHEMA}', got '{data.get('schema')}'"
            )
        if data.get("status") != "current":
            raise LineageValidationError(
                f"Invalid status: expected 'current', got '{data.get('status')}'"
            )
        if data.get("admission_authority") is not False:
            raise LineageValidationError("Lineage registry must declare admission_authority: false")
        if data.get("route_authority") not in (None, "none"):
            raise LineageValidationError("Lineage registry must not declare any route authority")

        lineages_raw = data.get("lineages")
        if not isinstance(lineages_raw, dict) or not lineages_raw:
            raise LineageValidationError(
                "Lineage registry must define a non-empty 'lineages' dictionary"
            )

        lineages: dict[str, CapabilityLineage] = {}
        identity_index: dict[tuple[str, str], str] = {}
        for raw in lineages_raw.values():
            if not isinstance(raw, Mapping):
                raise LineageValidationError("Each lineage record must be a YAML object")
            lineage = self._parse_lineage(raw)
            if lineage.lineage_id in lineages:
                raise LineageValidationError(f"Duplicate lineage_id: {lineage.lineage_id}")
            for identity in lineage.execution_identities:
                key = (identity.provider, identity.model)
                if key in identity_index:
                    raise LineageValidationError(
                        f"Duplicate execution identity {key[0]}/{key[1]} registered in both "
                        f"'{identity_index[key]}' and '{lineage.lineage_id}'"
                    )
                identity_index[key] = lineage.lineage_id
            lineages[lineage.lineage_id] = lineage

        for lineage in lineages.values():
            self._validate_capability_evidence_provenance(lineage)

        self._lineages = lineages
        self._identity_index = identity_index
        self._loaded = True
        return lineages

    def _validate_capability_evidence_provenance(self, lineage: CapabilityLineage) -> None:
        """Reject capability evidence whose workforce provenance contradicts identity.

        A capability calibration evidence record whose ref points into the
        machine-checkable model_workforce.yaml must resolve to a worker whose
        provider+model matches an execution identity of the SAME lineage.
        Pointing e.g. a gemini-3.7-flash-medium L3 record at workers.agy_flash_medium
        (which registers gemini-3.6-flash-medium) is a provenance contradiction
        and fails closed.  Records that are Owner-approved / pending durable
        writeback (no workforce ref) are not checked against the workforce file.
        """
        checks: list[tuple[str, str]] = []
        for ref in lineage.role_evidence:
            checks.append((ref.ref, ref.ref))
        for record in lineage.evidence:
            checks.append((record.id, record.id))
        workforce_refs = [
            (label, ref) for label, ref in checks if WORKFORCE_AUTHORITY_PATH_MARKER in ref
        ]
        if not workforce_refs:
            return

        try:
            snapshot = self._workforce_loader.load()
        except Exception as exc:
            raise LineageValidationError(
                f"Lineage '{lineage.lineage_id}' has capability evidence referencing "
                f"model_workforce.yaml but the workforce policy cannot be loaded: {exc}"
            ) from exc

        identity_models = {
            (identity.provider, identity.model) for identity in lineage.execution_identities
        }
        for label, ref in workforce_refs:
            worker = _resolve_worker_from_ref(ref, snapshot.workers)
            if worker is None:
                raise LineageValidationError(
                    f"Lineage '{lineage.lineage_id}' capability evidence '{label}' ref "
                    f"'{ref}' does not resolve to a registered workforce worker"
                )
            if (worker.provider, worker.model) not in identity_models:
                raise LineageValidationError(
                    f"Lineage '{lineage.lineage_id}' capability evidence '{label}' ref "
                    f"'{ref}' resolves to worker '{worker.worker_id}' "
                    f"({worker.provider}/{worker.model}) which is not an execution identity "
                    f"of this lineage; capability provenance contradicts referenced "
                    f"workforce identity"
                )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def lineages(self) -> dict[str, CapabilityLineage]:
        """Return all loaded lineages keyed by lineage_id."""
        self._ensure_loaded()
        return dict(self._lineages)

    def resolve_by_lineage_id(self, lineage_id: str) -> CapabilityLineage:
        """Resolve a lineage by its exact lineage_id. Unknown values fail closed."""
        self._ensure_loaded()
        lineage = self._lineages.get(str(lineage_id or "").strip())
        if lineage is None:
            raise LineageResolutionError(f"Unknown lineage_id: {lineage_id}")
        return lineage

    def resolve_by_execution_identity(self, provider: str, model: str) -> CapabilityLineage | None:
        """Resolve a lineage by an exact execution identity.

        Exact-match only: no fuzzy or marketing-text matching.  Returns None
        when the identity is not registered.  Raises LineageResolutionError
        only for registry inconsistencies (which are rejected at load time).
        """
        self._ensure_loaded()
        key = (str(provider or "").strip(), str(model or "").strip())
        lineage_id = self._identity_index.get(key)
        if lineage_id is None:
            return None
        return self._lineages[lineage_id]

    def resolve(
        self,
        *,
        lineage_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> CapabilityLineage:
        """Resolve a lineage by lineage_id or by exact provider+model identity.

        Unknown or ambiguous requests fail closed with LineageResolutionError.
        """
        if lineage_id:
            return self.resolve_by_lineage_id(lineage_id)
        if provider and model:
            lineage = self.resolve_by_execution_identity(provider, model)
            if lineage is None:
                raise LineageResolutionError(
                    f"No registered lineage for execution identity {provider}/{model}"
                )
            return lineage
        raise LineageResolutionError(
            "resolve requires lineage_id OR both provider and model (exact registered identity)"
        )

    def known_failure_families(self, lineage_id: str) -> tuple[KnownFailureFamily, ...]:
        """Return the known failure families for one lineage (always queryable)."""
        return self.resolve_by_lineage_id(lineage_id).known_failure_families


def _declaration_from_change_kind(
    change_kind: str | None,
    *,
    provider: str,
    model: str,
    description: str = "",
) -> ChangeDeclaration:
    """Translate a stable change-kind token into a ChangeDeclaration."""
    kind = str(change_kind or "").strip().lower()
    if kind == "new_lineage":
        return ChangeDeclaration(
            provider=provider, model=model, new_lineage=True, description=description
        )
    if kind == "alias_only":
        return ChangeDeclaration(
            provider=provider, model=model, alias_only=True, description=description
        )
    if kind == "transport_only":
        return ChangeDeclaration(
            provider=provider, model=model, transport_change=True, description=description
        )
    if kind == "cli_or_adapter_change":
        return ChangeDeclaration(
            provider=provider, model=model, cli_or_adapter_change=True, description=description
        )
    if kind == "prompt_template_or_thinking_change":
        return ChangeDeclaration(
            provider=provider,
            model=model,
            prompt_template_change=True,
            thinking_change=True,
            description=description,
        )
    if kind == "model_revision_or_backend_change":
        return ChangeDeclaration(
            provider=provider,
            model=model,
            model_revision_change=True,
            backend_change=True,
            description=description,
        )
    if kind == "unknown_material_change":
        return ChangeDeclaration(provider=provider, model=model, description=description)
    return ChangeDeclaration(provider=provider, model=model, description=description)


def classify_change(
    declaration: ChangeDeclaration,
    *,
    registered_as_alias: bool,
) -> ChangeClass:
    """Deterministically classify a change request into a ChangeClass.

    Materiality precedence (first match wins):
    NEW_LINEAGE > UNKNOWN_MATERIAL_CHANGE > MODEL_REVISION_OR_BACKEND_CHANGE >
    PROMPT_TEMPLATE_OR_THINKING_CHANGE > CLI_OR_ADAPTER_CHANGE >
    TRANSPORT_ONLY > ALIAS_ONLY.  With no declared flags a registered alias
    defaults to ALIAS_ONLY; anything else defaults to UNKNOWN_MATERIAL_CHANGE
    (fail closed).
    """
    if declaration.new_lineage:
        return ChangeClass.NEW_LINEAGE
    if declaration.model_revision_change or declaration.backend_change:
        return ChangeClass.MODEL_REVISION_OR_BACKEND_CHANGE
    if declaration.prompt_template_change or declaration.thinking_change:
        return ChangeClass.PROMPT_TEMPLATE_OR_THINKING_CHANGE
    if declaration.cli_or_adapter_change:
        return ChangeClass.CLI_OR_ADAPTER_CHANGE
    if declaration.transport_change:
        return ChangeClass.TRANSPORT_ONLY
    if declaration.alias_only:
        return ChangeClass.ALIAS_ONLY
    if registered_as_alias:
        return ChangeClass.ALIAS_ONLY
    if declaration.description:
        return ChangeClass.UNKNOWN_MATERIAL_CHANGE
    return ChangeClass.UNKNOWN_MATERIAL_CHANGE


def _all_evidence_refs(lineage: CapabilityLineage) -> list[EvidenceRef]:
    refs = list(lineage.role_evidence)
    for record in lineage.evidence:
        refs.append(
            EvidenceRef(
                ref=f"lineage:{lineage.lineage_id}/evidence:{record.id}",
                phase=record.phase,
                tier=record.tier,
                scope=record.scope,
                date=record.date,
                digest=record.digest,
                provenance=record.provenance,
            )
        )
    return refs


def _partition_evidence(
    lineage: CapabilityLineage | None,
    change_class: ChangeClass,
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    """Partition prior evidence into reusable vs invalidated for a change class."""
    if lineage is None:
        return (), ()
    refs = _all_evidence_refs(lineage)
    semantic = [ref for ref in refs if ref.scope is EvidenceScope.SEMANTIC]
    identity = [ref for ref in refs if ref.scope is EvidenceScope.IDENTITY_OR_TRANSPORT]

    if change_class is ChangeClass.ALIAS_ONLY:
        return (
            tuple(ref.to_dict() for ref in semantic),
            tuple(ref.to_dict() for ref in identity),
        )
    if change_class is ChangeClass.TRANSPORT_ONLY:
        return (
            tuple(ref.to_dict() for ref in semantic),
            tuple(ref.to_dict() for ref in identity),
        )
    if change_class is ChangeClass.CLI_OR_ADAPTER_CHANGE:
        return (
            tuple(ref.to_dict() for ref in semantic),
            tuple(ref.to_dict() for ref in identity),
        )
    if change_class is ChangeClass.PROMPT_TEMPLATE_OR_THINKING_CHANGE:
        return (
            tuple(ref.to_dict() for ref in identity),
            tuple(ref.to_dict() for ref in semantic),
        )
    if change_class is ChangeClass.MODEL_REVISION_OR_BACKEND_CHANGE:
        return (
            tuple(ref.to_dict() for ref in identity),
            tuple(ref.to_dict() for ref in semantic),
        )
    return (), tuple(ref.to_dict() for ref in refs)


class CalibrationPlanner:
    """Derives cumulative minimum-requalification plans from the registry."""

    def __init__(self, registry: ModelCapabilityLineageRegistry | None = None) -> None:
        self._registry = registry or ModelCapabilityLineageRegistry()

    def build_calibration_plan(
        self,
        *,
        provider: str,
        model: str,
        target_role: str,
        change_kind: str | None = None,
        description: str = "",
    ) -> CalibrationPlan:
        """Build a minimum-requalification plan for one model lineage.

        The model identity may be unresolved only when an explicit NEW_LINEAGE
        change is declared (full baseline).  Every other request for an
        unregistered identity fails closed.
        """
        declaration = _declaration_from_change_kind(
            change_kind, provider=provider, model=model, description=description
        )
        lineage = self._registry.resolve_by_execution_identity(provider, model)

        if lineage is None:
            if declaration.new_lineage:
                return self._new_lineage_plan(provider, model, target_role, declaration)
            raise LineageResolutionError(
                f"No registered lineage for execution identity {provider}/{model}; "
                "only an explicit new_lineage request can plan an unregistered model"
            )

        registered_as_alias = any(
            identity.provider == provider
            and identity.model == model
            and identity.identity_kind == "alias"
            for identity in lineage.execution_identities
        )
        change_class = classify_change(declaration, registered_as_alias=registered_as_alias)
        if change_class is ChangeClass.UNKNOWN_MATERIAL_CHANGE:
            return self._fail_closed_plan(lineage, provider, model, target_role, declaration)

        required, not_required, trial_reasons = self._derive_trials(lineage, change_class)
        reusable, invalidated = _partition_evidence(lineage, change_class)
        reasons = [
            f"change_class={change_class.value}",
            f"stable_floor={lineage.stable_floor} current_frontier={lineage.current_frontier}",
            f"target_role={target_role}",
            *trial_reasons,
        ]
        if change_class is ChangeClass.MODEL_REVISION_OR_BACKEND_CHANGE:
            reasons.append(
                "MODEL_REVISION_OR_BACKEND_CHANGE invalidates prior semantic evidence; "
                "family-name equivalence alone never re-claims capability"
            )
        if change_class is ChangeClass.PROMPT_TEMPLATE_OR_THINKING_CHANGE:
            reasons.append(
                "PROMPT_TEMPLATE_OR_THINKING_CHANGE treats semantic behavior as affected; "
                "rerun around the existing floor/frontier without replaying every lower tier"
            )
        if change_class in (
            ChangeClass.ALIAS_ONLY,
            ChangeClass.TRANSPORT_ONLY,
            ChangeClass.CLI_OR_ADAPTER_CHANGE,
        ):
            reasons.append(
                "lower-tier semantic capability evidence is reused; requalification starts "
                "from the stable floor, not from L1"
            )
        return CalibrationPlan(
            lineage_id=lineage.lineage_id,
            canonical_family=lineage.canonical_family,
            provider=provider,
            model=model,
            target_role=target_role,
            stable_floor=lineage.stable_floor,
            current_frontier=lineage.current_frontier,
            frontier_experimental=lineage.frontier_experimental,
            change_class=change_class,
            plan_status="PLANNED",
            reusable_evidence=reusable,
            invalidated_evidence=invalidated,
            required_trials=required,
            not_required_trials=not_required,
            failure_family_probes=self._failure_family_probes(lineage),
            reasons=tuple(reasons),
        )

    def _new_lineage_plan(
        self,
        provider: str,
        model: str,
        target_role: str,
        declaration: ChangeDeclaration,
    ) -> CalibrationPlan:
        full_baseline = tuple(
            CalibrationTrial(
                tier=tier,
                kind=TrialKind.FULL_BASELINE,
                reason=f"NEW_LINEAGE requires full baseline calibration at {tier}",
            )
            for tier in LINEAGE_TIERS[: LINEAGE_TIERS.index("L4")]
        )
        return CalibrationPlan(
            lineage_id="",
            canonical_family=f"{provider}/{model}",
            provider=provider,
            model=model,
            target_role=target_role,
            stable_floor=None,
            current_frontier=None,
            change_class=ChangeClass.NEW_LINEAGE,
            plan_status="PLANNED_FULL_BASELINE",
            required_trials=full_baseline,
            reasons=(
                "NEW_LINEAGE requires a full baseline calibration path from L0 to L3",
                declaration.description,
            ),
        )

    def _fail_closed_plan(
        self,
        lineage: CapabilityLineage,
        provider: str,
        model: str,
        target_role: str,
        declaration: ChangeDeclaration,
    ) -> CalibrationPlan:
        _, invalidated = _partition_evidence(lineage, ChangeClass.UNKNOWN_MATERIAL_CHANGE)
        return CalibrationPlan(
            lineage_id=lineage.lineage_id,
            canonical_family=lineage.canonical_family,
            provider=provider,
            model=model,
            target_role=target_role,
            stable_floor=lineage.stable_floor,
            current_frontier=lineage.current_frontier,
            frontier_experimental=lineage.frontier_experimental,
            change_class=ChangeClass.UNKNOWN_MATERIAL_CHANGE,
            plan_status="FAIL_CLOSED",
            invalidated_evidence=invalidated,
            reasons=(
                "UNKNOWN_MATERIAL_CHANGE fails closed and requests broader requalification",
                declaration.description,
            ),
        )

    def _derive_trials(
        self,
        lineage: CapabilityLineage,
        change_class: ChangeClass,
    ) -> tuple[tuple[CalibrationTrial, ...], tuple[NotRequiredTrial, ...], tuple[str, ...]]:
        floor = lineage.stable_floor
        frontier = lineage.current_frontier
        below_floor = tiers_strictly_below(floor)
        skip_reason = (
            "still-valid semantic capability evidence is reused; requalification "
            "starts from the stable floor, not from L1"
        )
        not_required = tuple(
            NotRequiredTrial(tier=tier, suite=f"{tier} full suite", reason=skip_reason)
            for tier in below_floor
        )

        if change_class is ChangeClass.ALIAS_ONLY:
            required = (
                CalibrationTrial(
                    tier=floor,
                    kind=TrialKind.IDENTITY_RESOLUTION,
                    reason="resolve and attest the requested alias to its registered lineage",
                ),
                CalibrationTrial(
                    tier=floor,
                    kind=TrialKind.TRANSPORT_PREFLIGHT,
                    reason="revalidate transport identity for the alias",
                ),
                CalibrationTrial(
                    tier=floor,
                    kind=TrialKind.STABLE_FLOOR_REGRESSION,
                    reason=f"one stable-floor regression at {floor}",
                    phase=EvidencePhase.FIRST_PASS,
                ),
                CalibrationTrial(
                    tier=frontier,
                    kind=TrialKind.FRONTIER_EVALUATION,
                    reason=f"frontier evaluation at {frontier}",
                    phase=EvidencePhase.FIRST_PASS,
                ),
                CalibrationTrial(
                    tier=frontier,
                    kind=TrialKind.FRONTIER_HIDDEN_PROBE,
                    reason=f"independent hidden probe at {frontier}",
                    phase=EvidencePhase.INDEPENDENT_HIDDEN_PROBE,
                ),
                CalibrationTrial(
                    tier=frontier,
                    kind=TrialKind.VERIFIER_GUIDED_REPAIR,
                    reason="optional one verifier-guided repair at the frontier",
                    phase=EvidencePhase.VERIFIER_GUIDED_REPAIR,
                    optional=True,
                ),
            )
            return (
                required + frontier_plus_one_trials(frontier),
                not_required,
                (
                    "alias requalification retains semantic capability evidence and revalidates identity/transport",
                ),
            )

        if change_class is ChangeClass.TRANSPORT_ONLY:
            return (
                (
                    CalibrationTrial(
                        tier=floor,
                        kind=TrialKind.TRANSPORT_PREFLIGHT,
                        reason="rerun transport preflight after transport change",
                    ),
                    CalibrationTrial(
                        tier=floor,
                        kind=TrialKind.PROTOCOL_TOOL_ISOLATION,
                        reason="rerun protocol/tool/isolation checks",
                    ),
                    CalibrationTrial(
                        tier=floor,
                        kind=TrialKind.STABLE_FLOOR_REGRESSION,
                        reason=f"one stable-floor regression at {floor}",
                        phase=EvidencePhase.FIRST_PASS,
                    ),
                    CalibrationTrial(
                        tier=frontier,
                        kind=TrialKind.FRONTIER_EVALUATION,
                        reason=f"frontier evaluation at {frontier}",
                        phase=EvidencePhase.FIRST_PASS,
                    ),
                    CalibrationTrial(
                        tier=frontier,
                        kind=TrialKind.FRONTIER_HIDDEN_PROBE,
                        reason=f"independent hidden probe at {frontier}",
                        phase=EvidencePhase.INDEPENDENT_HIDDEN_PROBE,
                        optional=True,
                    ),
                ),
                not_required,
                (
                    "transport-only change reuses semantic capability and revalidates transport/protocol/isolation",
                ),
            )

        if change_class is ChangeClass.CLI_OR_ADAPTER_CHANGE:
            return (
                (
                    CalibrationTrial(
                        tier=floor,
                        kind=TrialKind.PROTOCOL_TOOL_ISOLATION,
                        reason="rerun protocol/tool/isolation after CLI or adapter change",
                    ),
                    CalibrationTrial(
                        tier=floor,
                        kind=TrialKind.STABLE_FLOOR_REGRESSION,
                        reason=f"stable-floor regression at {floor}",
                        phase=EvidencePhase.FIRST_PASS,
                    ),
                    CalibrationTrial(
                        tier=frontier,
                        kind=TrialKind.FRONTIER_EVALUATION,
                        reason=f"frontier smoke at {frontier}",
                        phase=EvidencePhase.FIRST_PASS,
                    ),
                    CalibrationTrial(
                        tier=frontier,
                        kind=TrialKind.FRONTIER_HIDDEN_PROBE,
                        reason=f"independent hidden probe at {frontier}",
                        phase=EvidencePhase.INDEPENDENT_HIDDEN_PROBE,
                        optional=True,
                    ),
                ),
                not_required,
                (
                    "CLI or adapter change reuses semantic evidence provisionally and revalidates protocol/tool/isolation",
                ),
            )

        if change_class is ChangeClass.PROMPT_TEMPLATE_OR_THINKING_CHANGE:
            return (
                (
                    CalibrationTrial(
                        tier=floor,
                        kind=TrialKind.STABLE_FLOOR_REGRESSION,
                        reason=f"rerun around the stable floor {floor} because semantic behavior is affected",
                        phase=EvidencePhase.FIRST_PASS,
                    ),
                    CalibrationTrial(
                        tier=frontier,
                        kind=TrialKind.FRONTIER_EVALUATION,
                        reason=f"frontier evaluation at {frontier}",
                        phase=EvidencePhase.FIRST_PASS,
                    ),
                    CalibrationTrial(
                        tier=frontier,
                        kind=TrialKind.FRONTIER_HIDDEN_PROBE,
                        reason=f"independent hidden probe at {frontier}",
                        phase=EvidencePhase.INDEPENDENT_HIDDEN_PROBE,
                    ),
                    CalibrationTrial(
                        tier=frontier,
                        kind=TrialKind.VERIFIER_GUIDED_REPAIR,
                        reason="optional verifier-guided repair at the frontier",
                        phase=EvidencePhase.VERIFIER_GUIDED_REPAIR,
                        optional=True,
                    ),
                ),
                not_required,
                (
                    "prompt/thinking change treats semantic behavior as affected and reruns around floor/frontier without replaying every lower tier",
                ),
            )

        if change_class is ChangeClass.MODEL_REVISION_OR_BACKEND_CHANGE:
            required = (
                CalibrationTrial(
                    tier=floor,
                    kind=TrialKind.STABLE_FLOOR_REGRESSION,
                    reason=f"broader semantic requalification starts with stable-floor regression at {floor}",
                    phase=EvidencePhase.FIRST_PASS,
                ),
                CalibrationTrial(
                    tier=frontier,
                    kind=TrialKind.FRONTIER_EVALUATION,
                    reason=f"frontier evaluation at {frontier}",
                    phase=EvidencePhase.FIRST_PASS,
                ),
                CalibrationTrial(
                    tier=frontier,
                    kind=TrialKind.FRONTIER_HIDDEN_PROBE,
                    reason=f"independent hidden probe at {frontier}",
                    phase=EvidencePhase.INDEPENDENT_HIDDEN_PROBE,
                ),
                CalibrationTrial(
                    tier=frontier,
                    kind=TrialKind.VERIFIER_GUIDED_REPAIR,
                    reason="optional verifier-guided repair at the frontier",
                    phase=EvidencePhase.VERIFIER_GUIDED_REPAIR,
                    optional=True,
                ),
            )
            return (
                required + frontier_plus_one_trials(frontier),
                not_required,
                (
                    "model revision or backend change requires broader semantic requalification; prior semantic evidence is explicitly invalidated",
                ),
            )

        if change_class is ChangeClass.NEW_LINEAGE:
            full_baseline = tuple(
                CalibrationTrial(
                    tier=tier,
                    kind=TrialKind.FULL_BASELINE,
                    reason=f"NEW_LINEAGE full baseline at {tier}",
                )
                for tier in LINEAGE_TIERS[: LINEAGE_TIERS.index("L4")]
            )
            return full_baseline, (), ("NEW_LINEAGE requires a full baseline calibration path",)

        return (), not_required, ()

    def _failure_family_probes(self, lineage: CapabilityLineage) -> tuple[Mapping[str, str], ...]:
        """Adjacent-variant probes for known failure families.

        Fresh probes test adjacent variants rather than repeating exactly the
        same hidden case.
        """
        return tuple(
            {
                "family": family.family,
                "probe_kind": "adjacent_variant",
                "hidden_case": "fresh",
                "ref": family.ref,
            }
            for family in lineage.known_failure_families
        )

    def evidence_bundle(
        self,
        *,
        lineage_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Read-only evidence bundle for one resolved lineage."""
        lineage = self._registry.resolve(lineage_id=lineage_id, provider=provider, model=model)
        return {
            "schema": CALIBRATION_EVIDENCE_SCHEMA,
            "lineage_id": lineage.lineage_id,
            "canonical_family": lineage.canonical_family,
            "execution_identities": [
                identity.to_dict() for identity in lineage.execution_identities
            ],
            "stable_floor": lineage.stable_floor,
            "frontier": lineage.current_frontier,
            "frontier_experimental": lineage.frontier_experimental,
            "conditional_ceiling": lineage.conditional_ceiling,
            "experimental_ceiling": lineage.experimental_ceiling,
            "role_evidence": [ref.to_dict() for ref in lineage.role_evidence],
            "evidence": [record.to_dict() for record in lineage.evidence],
            "known_failure_families": [
                family.to_dict() for family in lineage.known_failure_families
            ],
            "experimental_notes": list(lineage.experimental_notes),
            "workforce_authority_refs": [ref.to_dict() for ref in lineage.workforce_authority_refs],
            "admission_authority": ADMISSION_AUTHORITY_SEPARATE,
            "disclaimer": ADMISSION_AUTHORITY_DISCLAIMER,
        }
