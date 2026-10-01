from __future__ import annotations

import re
from typing import Any, Mapping

MATRIX_SCHEMA = "nexus.core_effectiveness.g1_mutation_matrix.v1"
CLAIM_CEILING = "CONTROLLED_FIXTURE_CORRECTNESS_ONLY"
PASS_GATE = "G1_CONTROLLED_MUTATION_PASSED"
FAIL_GATE = "G1_CONTROLLED_MUTATION_FAILED"
IDENTITY_GATE = "G1_SUBJECT_IDENTITY_MISMATCH"

_REQUIRED_MUTANTS = tuple(f"M{index:02d}" for index in range(1, 16))
_ALLOWED_WITNESS_KINDS = frozenset({"SUBJECT_TEST", "EXTERNAL_BLACK_BOX_PROBE"})
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


class G1MatrixError(ValueError):
    """Raised when the controlled-mutation evidence contract is incomplete."""


def _require_text(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise G1MatrixError(reason)
    return value.strip()


def _validate_case(case: Mapping[str, Any], *, mutant: bool) -> str:
    case_id = _require_text(case.get("id"), "case_id_required")
    _require_text(case.get("description"), f"description_required:{case_id}")
    witness_kind = _require_text(case.get("witness_kind"), f"witness_kind_required:{case_id}")
    if witness_kind not in _ALLOWED_WITNESS_KINDS:
        raise G1MatrixError(f"invalid_witness_kind:{case_id}:{witness_kind}")
    _require_text(case.get("selector"), f"selector_required:{case_id}")

    expected_outcome = _require_text(
        case.get("expected_outcome"), f"expected_outcome_required:{case_id}"
    )
    required_outcome = "FAIL_CLOSED" if mutant else "ACCEPT"
    if expected_outcome != required_outcome:
        raise G1MatrixError(
            f"invalid_expected_outcome:{case_id}:{expected_outcome}:{required_outcome}"
        )

    signals = case.get("expected_signals")
    if (
        not isinstance(signals, list)
        or not signals
        or any(not isinstance(signal, str) or not signal.strip() for signal in signals)
    ):
        raise G1MatrixError(f"expected_signals_required:{case_id}")
    return case_id


def validate_g1_matrix(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the G1 evidence matrix without making any Core truth decision."""

    if manifest.get("schema") != MATRIX_SCHEMA:
        raise G1MatrixError("matrix_schema_mismatch")
    if manifest.get("claim_ceiling") != CLAIM_CEILING:
        raise G1MatrixError("claim_ceiling_mismatch")
    if manifest.get("auto_chain") is not False:
        raise G1MatrixError("auto_chain_must_be_false")

    subject = manifest.get("subject")
    if not isinstance(subject, Mapping):
        raise G1MatrixError("subject_required")
    if subject.get("repository") != "James3014/nexus-core":
        raise G1MatrixError("subject_repository_mismatch")
    revision = _require_text(subject.get("revision"), "subject_revision_required")
    if not _SHA40.fullmatch(revision):
        raise G1MatrixError("subject_revision_invalid")
    run_id = subject.get("ci_run_id")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise G1MatrixError("subject_ci_run_id_invalid")
    if subject.get("ci_conclusion") != "success":
        raise G1MatrixError("subject_ci_not_success")
    _require_text(subject.get("product_test_command"), "subject_product_test_command_required")
    passed = subject.get("product_test_passed")
    if isinstance(passed, bool) or not isinstance(passed, int) or passed < 1:
        raise G1MatrixError("subject_product_test_passed_invalid")

    mutants = manifest.get("mutants")
    controls = manifest.get("controls")
    if not isinstance(mutants, list):
        raise G1MatrixError("mutants_required")
    if not isinstance(controls, list) or not controls:
        raise G1MatrixError("controls_required")

    seen: set[str] = set()
    mutant_ids: list[str] = []
    for raw in mutants:
        if not isinstance(raw, Mapping):
            raise G1MatrixError("mutant_must_be_object")
        case_id = _validate_case(raw, mutant=True)
        if case_id in seen:
            raise G1MatrixError(f"duplicate_case_id:{case_id}")
        seen.add(case_id)
        mutant_ids.append(case_id)

    expected = set(_REQUIRED_MUTANTS)
    actual = set(mutant_ids)
    missing = sorted(expected - actual)
    if missing:
        raise G1MatrixError(f"missing_mutants:{','.join(missing)}")
    extra = sorted(actual - expected)
    if extra:
        raise G1MatrixError(f"unexpected_mutants:{','.join(extra)}")

    for raw in controls:
        if not isinstance(raw, Mapping):
            raise G1MatrixError("control_must_be_object")
        case_id = _validate_case(raw, mutant=False)
        if case_id in seen:
            raise G1MatrixError(f"duplicate_case_id:{case_id}")
        seen.add(case_id)

    return dict(manifest)


def _case_passed(case: Mapping[str, Any], observation: Mapping[str, Any] | None) -> bool:
    if observation is None or observation.get("executed") is not True:
        return False
    if observation.get("observed_outcome") != case.get("expected_outcome"):
        return False
    observed_signals = observation.get("observed_signals")
    if not isinstance(observed_signals, list):
        return False
    expected_signals = case.get("expected_signals")
    if not isinstance(expected_signals, list):
        return False
    if not set(expected_signals).issubset(set(observed_signals)):
        return False
    evidence = observation.get("evidence")
    return isinstance(evidence, str) and bool(evidence.strip())


def evaluate_g1_results(
    manifest: Mapping[str, Any],
    observations: Mapping[str, Mapping[str, Any]],
    *,
    observed_subject_revision: str,
) -> dict[str, Any]:
    """Project controlled mutation evidence into a bounded G1 gate result."""

    checked = validate_g1_matrix(manifest)
    subject = checked["subject"]
    expected_revision = str(subject["revision"])
    if observed_subject_revision != expected_revision:
        return {
            "schema": "nexus.core_effectiveness.g1_mutation_report.v1",
            "authority": "RESEARCH_OBSERVATION_ONLY",
            "claim_ceiling": CLAIM_CEILING,
            "auto_chain": False,
            "gate": IDENTITY_GATE,
            "subject_revision": expected_revision,
            "observed_subject_revision": observed_subject_revision,
            "subject_revision_match": False,
            "mutants_total": len(checked["mutants"]),
            "mutants_detected": 0,
            "controls_total": len(checked["controls"]),
            "controls_passed": 0,
            "deterministic_mutant_escape_count": len(checked["mutants"]),
            "false_block_control_count": 0,
            "failed_case_ids": sorted(
                [case["id"] for case in checked["mutants"]]
            ),
        }

    failed_mutants: list[str] = []
    failed_controls: list[str] = []
    for case in checked["mutants"]:
        case_id = str(case["id"])
        if not _case_passed(case, observations.get(case_id)):
            failed_mutants.append(case_id)
    for case in checked["controls"]:
        case_id = str(case["id"])
        if not _case_passed(case, observations.get(case_id)):
            failed_controls.append(case_id)

    failed_case_ids = sorted([*failed_mutants, *failed_controls])
    gate = PASS_GATE if not failed_case_ids else FAIL_GATE
    return {
        "schema": "nexus.core_effectiveness.g1_mutation_report.v1",
        "authority": "RESEARCH_OBSERVATION_ONLY",
        "claim_ceiling": CLAIM_CEILING,
        "auto_chain": False,
        "gate": gate,
        "subject_revision": expected_revision,
        "observed_subject_revision": observed_subject_revision,
        "subject_revision_match": True,
        "mutants_total": len(checked["mutants"]),
        "mutants_detected": len(checked["mutants"]) - len(failed_mutants),
        "controls_total": len(checked["controls"]),
        "controls_passed": len(checked["controls"]) - len(failed_controls),
        "deterministic_mutant_escape_count": len(failed_mutants),
        "false_block_control_count": len(failed_controls),
        "failed_case_ids": failed_case_ids,
    }
