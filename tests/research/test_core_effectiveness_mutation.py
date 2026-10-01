from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from nexus.research.core_effectiveness_mutation import (
    G1MatrixError,
    evaluate_g1_results,
    validate_g1_matrix,
)

MUTANT_IDS = [f"M{i:02d}" for i in range(1, 16)]


def _manifest() -> dict[str, object]:
    return {
        "schema": "nexus.core_effectiveness.g1_mutation_matrix.v1",
        "study_issue": "James3014/Nexus-new#1278",
        "gate_issue": "James3014/Nexus-new#1286",
        "claim_ceiling": "CONTROLLED_FIXTURE_CORRECTNESS_ONLY",
        "auto_chain": False,
        "subject": {
            "repository": "James3014/nexus-core",
            "revision": "2c9b746d0ae2da87af4a252b39eb09ae623d7467",
            "ci_run_id": 36842914100,
            "ci_conclusion": "success",
            "product_test_command": "uv run pytest -q tests/product",
            "product_test_passed": 1113,
            "product_test_deselected": 1,
        },
        "mutants": [
            {
                "id": mutant_id,
                "description": f"fault {mutant_id}",
                "witness_kind": "SUBJECT_TEST",
                "selector": f"tests/product/test_fake.py::test_{mutant_id.lower()}",
                "expected_outcome": "FAIL_CLOSED",
                "expected_signals": [f"SIG_{mutant_id}"],
            }
            for mutant_id in MUTANT_IDS
        ],
        "controls": [
            {
                "id": "C01",
                "description": "valid control",
                "witness_kind": "SUBJECT_TEST",
                "selector": "tests/product/test_fake.py::test_control",
                "expected_outcome": "ACCEPT",
                "expected_signals": ["VERIFIED"],
            }
        ],
    }


def _observations(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = {}
    for case in [*manifest["mutants"], *manifest["controls"]]:
        rows[case["id"]] = {
            "executed": True,
            "observed_outcome": case["expected_outcome"],
            "observed_signals": list(case["expected_signals"]),
            "evidence": "exact-subject-test",
        }
    return rows


def test_complete_matrix_with_all_expected_witnesses_passes_g1() -> None:
    manifest = _manifest()
    validate_g1_matrix(manifest)

    report = evaluate_g1_results(
        manifest,
        _observations(manifest),
        observed_subject_revision=manifest["subject"]["revision"],
    )

    assert report["gate"] == "G1_CONTROLLED_MUTATION_PASSED"
    assert report["mutants_total"] == 15
    assert report["mutants_detected"] == 15
    assert report["controls_total"] == 1
    assert report["controls_passed"] == 1
    assert report["deterministic_mutant_escape_count"] == 0
    assert report["false_block_control_count"] == 0
    assert report["claim_ceiling"] == "CONTROLLED_FIXTURE_CORRECTNESS_ONLY"
    assert report["auto_chain"] is False


def test_missing_declared_mutant_fails_closed() -> None:
    manifest = _manifest()
    manifest["mutants"] = manifest["mutants"][:-1]

    with pytest.raises(G1MatrixError, match="missing_mutants:M15"):
        validate_g1_matrix(manifest)


def test_duplicate_case_identity_fails_closed() -> None:
    manifest = _manifest()
    manifest["mutants"].append(copy.deepcopy(manifest["mutants"][0]))

    with pytest.raises(G1MatrixError, match="duplicate_case_id:M01"):
        validate_g1_matrix(manifest)


def test_mutant_escape_blocks_g1() -> None:
    manifest = _manifest()
    observations = _observations(manifest)
    observations["M07"]["observed_outcome"] = "ACCEPT"
    observations["M07"]["observed_signals"] = ["VERIFIED"]

    report = evaluate_g1_results(
        manifest,
        observations,
        observed_subject_revision=manifest["subject"]["revision"],
    )

    assert report["gate"] == "G1_CONTROLLED_MUTATION_FAILED"
    assert report["deterministic_mutant_escape_count"] == 1
    assert report["failed_case_ids"] == ["M07"]


def test_valid_control_false_block_blocks_g1() -> None:
    manifest = _manifest()
    observations = _observations(manifest)
    observations["C01"]["observed_outcome"] = "FAIL_CLOSED"
    observations["C01"]["observed_signals"] = ["FORBIDDEN_PATH"]

    report = evaluate_g1_results(
        manifest,
        observations,
        observed_subject_revision=manifest["subject"]["revision"],
    )

    assert report["gate"] == "G1_CONTROLLED_MUTATION_FAILED"
    assert report["false_block_control_count"] == 1
    assert report["failed_case_ids"] == ["C01"]


def test_repository_g1_matrix_is_complete() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (root / "docs/research/nexus_core_effectiveness_v1/g1_mutation_matrix.json").read_text(
            encoding="utf-8"
        )
    )

    checked = validate_g1_matrix(manifest)

    assert checked["subject"]["revision"] == "2c9b746d0ae2da87af4a252b39eb09ae623d7467"
    assert [case["id"] for case in checked["mutants"]] == MUTANT_IDS
    assert len(checked["controls"]) >= 1


def test_subject_revision_mismatch_blocks_g1() -> None:
    manifest = _manifest()

    report = evaluate_g1_results(
        manifest,
        _observations(manifest),
        observed_subject_revision="0" * 40,
    )

    assert report["gate"] == "G1_SUBJECT_IDENTITY_MISMATCH"
    assert report["subject_revision_match"] is False
