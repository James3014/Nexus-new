"""Executable contract for the semantic-authority delta classifier."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from nexus.contracts.semantic_authority_delta import (
    DIRECT_CANONICAL,
    GOVERNED_REQUIRED,
    SemanticAuthorityDelta,
    classify_semantic_authority_delta,
)


AUTHORITY_DIMENSIONS = (
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
)
# Independent fixed oracle from Issue #401's enumerated authority contract.
EXPECTED_AUTHORITY_DIMENSIONS = frozenset(AUTHORITY_DIMENSIONS)
EXPECTED_AUTHORITY_DIMENSION_COUNT = 23


class SpoofStr(str):
    def __hash__(self) -> int:
        return hash("evidence_provenance_writeback")

    def __eq__(self, other: object) -> bool:
        return other == "evidence_provenance_writeback"


class ExplodingOuterMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError("hostile getitem")

    def __iter__(self):
        raise RuntimeError("hostile iter")

    def __len__(self) -> int:
        return 1


class ExplodingNestedMapping(Mapping[str, bool]):
    def __getitem__(self, key: str) -> bool:
        raise RuntimeError("hostile nested getitem")

    def __iter__(self):
        raise RuntimeError("hostile nested iter")

    def __len__(self) -> int:
        return len(EXPECTED_AUTHORITY_DIMENSIONS)

    def items(self):
        raise RuntimeError("hostile nested items")

    def values(self):
        raise RuntimeError("hostile nested values")


class ItemsExplodingNestedMapping(dict[str, bool]):
    def items(self):
        raise RuntimeError("hostile nested items")


class ValuesExplodingNestedMapping(dict[str, bool]):
    def values(self):
        raise RuntimeError("hostile nested values")


class InconsistentNestedMapping(Mapping[str, bool]):
    def __iter__(self):
        return iter(EXPECTED_AUTHORITY_DIMENSIONS)

    def __len__(self) -> int:
        return len(EXPECTED_AUTHORITY_DIMENSIONS)

    def __getitem__(self, key: str) -> bool:
        return key != "autonomy"

    def items(self):
        return ((key, True) for key in EXPECTED_AUTHORITY_DIMENSIONS)

    def values(self):
        return (True for _ in EXPECTED_AUTHORITY_DIMENSIONS)


class ExplodingFilesTuple(tuple[str, ...]):
    def __iter__(self):
        raise RuntimeError("hostile changed-files iter")


class SpoofFilesTuple(tuple[str, ...]):
    def __iter__(self):
        yield SpoofStr("AGENTS.md")


def test_independent_authority_dimension_oracle_is_complete():
    assert EXPECTED_AUTHORITY_DIMENSION_COUNT == len(EXPECTED_AUTHORITY_DIMENSIONS)
    assert EXPECTED_AUTHORITY_DIMENSIONS == {
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
    }


def valid_delta(**overrides: object) -> SemanticAuthorityDelta:
    values: dict[str, object] = {
        "owner_authorized": True,
        "write_kind": "evidence_provenance_writeback",
        "evidence_change": "additive_append_only",
        "bound_source": True,
        "bound_task": True,
        "bound_attempt": True,
        "bound_receipt": True,
        "bound_provenance": True,
        "deletion": False,
        "historical_rewrite": False,
        "receipt_mutation": False,
        "authority_transition": False,
        "authority_unchanged": {key: True for key in AUTHORITY_DIMENSIONS},
        "bounded_scope_declared": True,
        "focused_verifier_declared": True,
        "changed_file_audit_declared": True,
        "no_deletion_declared": True,
        "diff_check_declared": True,
        "protected_action_bundled": False,
    }
    values.update(overrides)
    return SemanticAuthorityDelta(**values)


def test_additive_calibration_provenance_writeback_is_direct():
    assert classify_semantic_authority_delta(valid_delta()) == DIRECT_CANONICAL


def test_non_authoritative_descriptive_correction_is_direct():
    assert classify_semantic_authority_delta(
        valid_delta(write_kind="descriptive_correction")
    ) == DIRECT_CANONICAL


@pytest.mark.parametrize("field", ("write_kind", "evidence_change"))
def test_str_subclasses_cannot_spoof_exact_tokens(field: str):
    token = "evidence_provenance_writeback" if field == "write_kind" else "additive_append_only"
    assert classify_semantic_authority_delta(valid_delta(**{field: SpoofStr(token)})) == GOVERNED_REQUIRED


@pytest.mark.parametrize("mapping", (ExplodingOuterMapping(),))
def test_hostile_outer_mapping_is_governed(mapping: Mapping[str, object]):
    assert classify_semantic_authority_delta(mapping) == GOVERNED_REQUIRED


@pytest.mark.parametrize("unchanged", (ExplodingNestedMapping(),))
def test_hostile_nested_mapping_is_governed(unchanged: Mapping[str, bool]):
    assert classify_semantic_authority_delta(valid_delta(authority_unchanged=unchanged)) == GOVERNED_REQUIRED


@pytest.mark.parametrize(
    "unchanged",
    (
        ItemsExplodingNestedMapping({key: True for key in EXPECTED_AUTHORITY_DIMENSIONS}),
        ValuesExplodingNestedMapping({key: True for key in EXPECTED_AUTHORITY_DIMENSIONS}),
    ),
)
def test_untrusted_nested_views_are_not_consulted(unchanged: Mapping[str, bool]):
    assert classify_semantic_authority_delta(valid_delta(authority_unchanged=unchanged)) == DIRECT_CANONICAL


def test_inconsistent_nested_mapping_snapshot_is_governed():
    assert classify_semantic_authority_delta(
        valid_delta(authority_unchanged=InconsistentNestedMapping())
    ) == GOVERNED_REQUIRED


@pytest.mark.parametrize(
    "changed_files",
    (
        ExplodingFilesTuple(("AGENTS.md",)),
        SpoofFilesTuple(("AGENTS.md",)),
        (SpoofStr("AGENTS.md"),),
    ),
)
def test_changed_files_requires_exact_builtin_tuple_and_paths(changed_files: tuple[str, ...]):
    result = classify_semantic_authority_delta(valid_delta(changed_files=changed_files))
    assert result in {DIRECT_CANONICAL, GOVERNED_REQUIRED}
    assert result == GOVERNED_REQUIRED


@pytest.mark.parametrize(
    "field",
    (
        "owner_authorized",
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
    ),
)
def test_any_unsafe_top_level_assertion_is_governed(field: str):
    value = (
        False
        if field in {
            "owner_authorized",
            "bounded_scope_declared",
            "focused_verifier_declared",
            "changed_file_audit_declared",
            "no_deletion_declared",
            "diff_check_declared",
        }
        else True
    )
    assert classify_semantic_authority_delta(valid_delta(**{field: value})) == GOVERNED_REQUIRED


@pytest.mark.parametrize("dimension", AUTHORITY_DIMENSIONS)
def test_every_authority_dimension_must_be_explicitly_unchanged(dimension: str):
    unchanged = dict(valid_delta().authority_unchanged)
    unchanged[dimension] = False
    assert classify_semantic_authority_delta(
        valid_delta(authority_unchanged=unchanged)
    ) == GOVERNED_REQUIRED


@pytest.mark.parametrize(
    "field",
    ("bound_source", "bound_task", "bound_attempt", "bound_receipt", "bound_provenance"),
)
def test_missing_bound_identity_is_governed(field: str):
    assert classify_semantic_authority_delta(valid_delta(**{field: False})) == GOVERNED_REQUIRED


def test_contradictory_evidence_only_and_authority_change_is_governed():
    unchanged = dict(valid_delta().authority_unchanged)
    unchanged["default_route"] = False
    assert classify_semantic_authority_delta(
        valid_delta(write_kind="evidence_provenance_writeback", authority_unchanged=unchanged)
    ) == GOVERNED_REQUIRED


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"owner_authorized": True},
        {"owner_authorized": "yes"},
        {"owner_authorized": True, "unknown": False},
    ),
)
def test_missing_unknown_or_malformed_mapping_is_governed(payload: dict[str, object]):
    assert classify_semantic_authority_delta(payload) == GOVERNED_REQUIRED


def test_filename_or_tiny_diff_never_decides_result():
    assert classify_semantic_authority_delta(
        valid_delta(changed_files=("AGENTS.md",), diff_lines=1)
    ) == DIRECT_CANONICAL
    assert classify_semantic_authority_delta(
        valid_delta(changed_files=("protected.py",), diff_lines=1, owner_authorized=False)
    ) == GOVERNED_REQUIRED


def test_malformed_descriptive_metadata_is_governed():
    assert classify_semantic_authority_delta(valid_delta(changed_files=["README.md"])) == GOVERNED_REQUIRED
    assert classify_semantic_authority_delta(valid_delta(diff_lines=-1)) == GOVERNED_REQUIRED


def test_direct_delegated_is_not_a_classifier_outcome():
    assert "DIRECT_DELEGATED" not in {DIRECT_CANONICAL, GOVERNED_REQUIRED}
