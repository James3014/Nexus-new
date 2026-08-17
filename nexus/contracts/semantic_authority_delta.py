"""Pure, fail-closed classification of semantic-authority evidence writebacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, Mapping

DIRECT_CANONICAL: Final = "DIRECT_CANONICAL"
GOVERNED_REQUIRED: Final = "GOVERNED_REQUIRED"
ClassifierResult = Literal["DIRECT_CANONICAL", "GOVERNED_REQUIRED"]

_DIMENSIONS: Final = frozenset(
    {
    "autonomy",
    "roles_capabilities",
    "workforce_admission",
    "provider_model_worker_authority",
    "default_route",
    "semantic_authority_lineage",
    "parser_verifier",
    "independent_review",
    "forbidden_actions",
    "protected_ref_actions",
    "claim_ceilings",
    "capability_planner",
    "lifecycle",
    "candidate",
    "approval",
    "integration",
    "merge",
    "release",
    "security",
    "migration_schema",
    "production_data",
    "production",
    "public_claim",
})


@dataclass(frozen=True, slots=True)
class SemanticAuthorityDelta:
    """Typed evidence required to keep a writeback in the direct lane."""

    owner_authorized: bool
    write_kind: str
    evidence_change: str
    bound_source: bool
    bound_task: bool
    bound_attempt: bool
    bound_receipt: bool
    bound_provenance: bool
    deletion: bool
    historical_rewrite: bool
    receipt_mutation: bool
    authority_transition: bool
    authority_unchanged: Mapping[str, bool]
    bounded_scope_declared: bool
    focused_verifier_declared: bool
    changed_file_audit_declared: bool
    no_deletion_declared: bool
    diff_check_declared: bool
    protected_action_bundled: bool
    # Descriptive metadata is deliberately not inspected by the classifier.
    changed_files: tuple[str, ...] = ()
    diff_lines: int | None = None


SemanticAuthorityDeltaEnvelope = SemanticAuthorityDelta

_REQUIRED_FIELDS: Final = frozenset(SemanticAuthorityDelta.__dataclass_fields__)


def _typed_envelope(
    value: SemanticAuthorityDelta | Mapping[str, Any],
) -> SemanticAuthorityDelta | None:
    if isinstance(value, SemanticAuthorityDelta):
        return value
    if not isinstance(value, Mapping):
        return None
    try:
        if set(value) != _REQUIRED_FIELDS:
            return None
        return SemanticAuthorityDelta(**dict(value))
    except Exception:
        return None


def _strict_bool(value: object) -> bool:
    return type(value) is bool


def classify_semantic_authority_delta(
    envelope: SemanticAuthorityDelta | Mapping[str, Any],
) -> ClassifierResult:
    """Return the only two permitted lane outcomes, failing closed on uncertainty."""

    item = _typed_envelope(envelope)
    if item is None:
        return GOVERNED_REQUIRED

    boolean_fields = (
        "owner_authorized",
        "bound_source",
        "bound_task",
        "bound_attempt",
        "bound_receipt",
        "bound_provenance",
        "deletion",
        "historical_rewrite",
        "receipt_mutation",
        "authority_transition",
        "bounded_scope_declared",
        "focused_verifier_declared",
        "changed_file_audit_declared",
        "no_deletion_declared",
        "diff_check_declared",
        "protected_action_bundled",
    )
    if any(not _strict_bool(getattr(item, field)) for field in boolean_fields):
        return GOVERNED_REQUIRED
    if type(item.write_kind) is not str or item.write_kind not in {
        "evidence_provenance_writeback",
        "descriptive_correction",
    }:
        return GOVERNED_REQUIRED
    if type(item.evidence_change) is not str or item.evidence_change != "additive_append_only":
        return GOVERNED_REQUIRED
    if not isinstance(item.authority_unchanged, Mapping):
        return GOVERNED_REQUIRED
    if not _changed_files_valid(item.changed_files):
        return GOVERNED_REQUIRED
    if item.diff_lines is not None and (
        type(item.diff_lines) is not int or item.diff_lines < 0
    ):
        return GOVERNED_REQUIRED
    if not _authority_dimensions_unchanged(item.authority_unchanged):
        return GOVERNED_REQUIRED

    safe = (
        item.owner_authorized
        and item.bound_source
        and item.bound_task
        and item.bound_attempt
        and item.bound_receipt
        and item.bound_provenance
        and not item.deletion
        and not item.historical_rewrite
        and not item.receipt_mutation
        and not item.authority_transition
        and item.bounded_scope_declared
        and item.focused_verifier_declared
        and item.changed_file_audit_declared
        and item.no_deletion_declared
        and item.diff_check_declared
        and not item.protected_action_bundled
    )
    return DIRECT_CANONICAL if safe else GOVERNED_REQUIRED


def _authority_dimensions_unchanged(value: Mapping[str, bool]) -> bool:
    """Materialize one stable snapshot of a possibly hostile mapping."""

    try:
        snapshot = dict(value)
        if set(snapshot) != _DIMENSIONS:
            return False
        return all(
            type(key) is str and type(item_value) is bool and item_value is True
            for key, item_value in snapshot.items()
        )
    except Exception:
        return False


def _changed_files_valid(value: object) -> bool:
    """Validate descriptive file metadata without trusting tuple subclasses."""

    try:
        return type(value) is tuple and all(type(path) is str for path in value)
    except Exception:
        return False
