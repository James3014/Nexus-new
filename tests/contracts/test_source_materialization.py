from __future__ import annotations

from copy import deepcopy

from nexus.contracts.source_materialization import (
    DIRECT_SLICE,
    NO_SOURCE,
    RAW_SOURCE,
    REDUCED_CAPSULE,
    SOURCE_MATERIALIZATION_CLAIM_CEILING,
    SOURCE_MATERIALIZATION_SCHEMA,
    build_source_materialization_projection,
    validate_source_materialization_projection,
)


def _selected_source() -> dict[str, object]:
    return {
        "path": "nexus/services/online_nexus_context.py",
        "symbol": "build_online_nexus_context",
        "ranges": [[430, 510]],
        "content_hash": "sha256:source-content",
    }


def _identity() -> dict[str, str]:
    return {
        "repository": "James3014/Nexus-new",
        "revision": "deadbeef",
        "tree": "cafebabe",
        "source_hash": "sha256:source-root",
    }


def test_direct_slice_projection_is_bounded_assist_only_context() -> None:
    payload = build_source_materialization_projection(
        strategy=DIRECT_SLICE,
        selected_sources=[_selected_source()],
        **_identity(),
    )

    assert payload["schema"] == SOURCE_MATERIALIZATION_SCHEMA
    assert payload["status"] == "PASS"
    assert payload["strategy"] == DIRECT_SLICE
    assert payload["claim_ceiling"] == SOURCE_MATERIALIZATION_CLAIM_CEILING
    assert payload["selection_authority"] == "CapabilityPlanner"
    assert payload["public_claim_allowed"] is False
    assert payload["reduction"] == {}
    assert payload["selected_sources"] == [_selected_source()]
    assert payload["blockers"] == []
    assert payload["materialization_hash"]


def test_reduced_capsule_binds_reducer_lineage_and_possible_omissions() -> None:
    payload = build_source_materialization_projection(
        strategy=REDUCED_CAPSULE,
        selected_sources=[_selected_source()],
        reduction={
            "reducer_operation_id": "reduce-op-001",
            "reducer_worker": "local-advisor",
            "reducer_provider": "ollama",
            "reducer_model": "qwen2.5-s2t-advisor:3b",
            "input_hash": "sha256:reducer-input",
            "output_hash": "sha256:reducer-output",
            "original_chars": 12000,
            "reduced_chars": 2400,
            "original_tokens": 3000,
            "reduced_tokens": 600,
            "uncertainties": ["cross-file invariant may require raw source"],
            "omitted_regions": ["unselected helper implementations"],
        },
        escalation={
            "raw_source_required": True,
            "reason": "authority-sensitive caller requires exact source",
        },
        **_identity(),
    )

    assert payload["status"] == "PASS"
    assert payload["reduction"]["reducer_operation_id"] == "reduce-op-001"
    assert payload["reduction"]["original_chars"] == 12000
    assert payload["reduction"]["reduced_chars"] == 2400
    assert payload["escalation"] == {
        "raw_source_required": True,
        "reason": "authority-sensitive caller requires exact source",
    }


def test_raw_source_is_explicit_and_does_not_smuggle_a_reducer() -> None:
    payload = build_source_materialization_projection(
        strategy=RAW_SOURCE,
        selected_sources=[_selected_source()],
        escalation={"raw_source_required": True, "reason": "high semantic risk"},
        **_identity(),
    )

    assert payload["status"] == "PASS"
    assert payload["strategy"] == RAW_SOURCE
    assert payload["reduction"] == {}


def test_no_source_is_a_truthful_terminal_projection() -> None:
    payload = build_source_materialization_projection(strategy=NO_SOURCE)

    assert payload["status"] == "PASS"
    assert payload["selected_sources"] == []
    assert payload["source_identity"] == {
        "repository": "",
        "revision": "",
        "tree": "",
        "source_hash": "",
    }
    assert payload["claim_ceiling"] == SOURCE_MATERIALIZATION_CLAIM_CEILING


def test_reduced_capsule_fails_closed_when_lineage_or_size_is_invalid() -> None:
    payload = build_source_materialization_projection(
        strategy=REDUCED_CAPSULE,
        selected_sources=[_selected_source()],
        reduction={
            "reducer_operation_id": "",
            "input_hash": "",
            "output_hash": "",
            "original_chars": 100,
            "reduced_chars": 200,
            "uncertainties": [],
            "omitted_regions": [],
        },
        **_identity(),
    )

    assert payload["status"] == "RETURN"
    assert "reduction_missing:reducer_operation_id" in payload["blockers"]
    assert "reduction_missing:input_hash" in payload["blockers"]
    assert "reduction_missing:output_hash" in payload["blockers"]
    assert "reduction_not_smaller_than_original" in payload["blockers"]


def test_non_reduced_strategy_rejects_reduction_payload() -> None:
    payload = build_source_materialization_projection(
        strategy=DIRECT_SLICE,
        selected_sources=[_selected_source()],
        reduction={
            "reducer_operation_id": "reduce-op-001",
            "input_hash": "sha256:input",
            "output_hash": "sha256:output",
            "original_chars": 100,
            "reduced_chars": 50,
            "uncertainties": [],
            "omitted_regions": [],
        },
        **_identity(),
    )

    assert payload["status"] == "RETURN"
    assert "reduction_requires_reduced_capsule_strategy" in payload["blockers"]


def test_projection_tamper_and_authority_widening_fail_closed() -> None:
    payload = build_source_materialization_projection(
        strategy=DIRECT_SLICE,
        selected_sources=[_selected_source()],
        **_identity(),
    )
    tampered = deepcopy(payload)
    tampered["selected_sources"][0]["content_hash"] = "sha256:substituted"
    tampered["claim_ceiling"] = "VERIFIED"
    tampered["selection_authority"] = "SourceReducer"
    tampered["public_claim_allowed"] = True
    tampered["runtime_update_allowed"] = True

    blockers = validate_source_materialization_projection(tampered)
    assert "source_materialization_hash_mismatch" in blockers
    assert "invalid_source_materialization_claim_ceiling" in blockers
    assert "source_materialization_must_not_select_authority" in blockers
    assert "source_materialization_must_not_unlock_public_claim" in blockers
    assert "source_materialization_must_not_update_runtime" in blockers


def test_source_identity_and_raw_escalation_reason_are_required_when_applicable() -> None:
    payload = build_source_materialization_projection(
        strategy=DIRECT_SLICE,
        selected_sources=[_selected_source()],
        escalation={"raw_source_required": True, "reason": ""},
    )

    assert payload["status"] == "RETURN"
    assert "missing_source_identity:repository" in payload["blockers"]
    assert "missing_source_identity:revision" in payload["blockers"]
    assert "missing_source_identity:source_hash" in payload["blockers"]
    assert "raw_source_escalation_reason_missing" in payload["blockers"]
