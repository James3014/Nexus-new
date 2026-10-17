"""Tests for runbook_compliance module (V4-C.2)."""

import importlib.util

from nexus.services.local_heal.evaluation_gate import (
    AffectedSuiteManifest,
    bind_affected_regression_suite,
)
from nexus.services.local_heal.evaluation_gate import (
    TestResult as EvaluationTestResult,
)


def _make_receipt(**overrides):
    """Helper to create a valid receipt with overrides."""
    base = {
        "task_id": "TEST001",
        "repo": "test",
        "source_git_sha": "abc123",
        "execution_mode": "real",
        "provider": "ollama",
        "model": "qwen2.5-coder:7b",
        "model_calls": 1,
        "cloud_api_used": False,
        "deterministic_fallback_used": False,
        "match_authority": "verbatim",
        "success_attribution": "model_patch_success",
        "export_classification": "model_patch_success_candidate",
        "task_scoped": True,
        "verifier_status": "passed",
        "blocker_type": None,
        "public_claim_allowed": False,
        "training_eligible": False,
        "final_lane": "verifier_passed_by_execution",
        "final_status": "INTERNAL_REPAIR_PASS_INTERNAL_ONLY",
    }
    base.update(overrides)
    return base


# ─── Valid receipt tests ─────────────────────────────────────────────────────


def test_valid_direct_patch_receipt() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


def test_valid_canonical_recovery_receipt() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


def test_valid_env_blocked_receipt() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


# ─── Attribution violation tests ─────────────────────────────────────────────


def test_success_with_null_authority() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


def test_fuzzy_candidate_only_success() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


def test_canonical_recovery_collapsed() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


def test_model_calls_zero_with_success() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


# ─── Governance violation tests ──────────────────────────────────────────────


def test_public_claim_allowed() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


def test_training_eligible() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


def test_cloud_api_used() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


# ─── Verifier violation tests ────────────────────────────────────────────────


def test_task_scoped_false_on_pass() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


# ─── Model policy tests ──────────────────────────────────────────────────────


def test_3b_treated_as_validated() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


# ─── Lane classification tests ───────────────────────────────────────────────


def test_env_blocked_classified_as_model_success() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


# ─── Schema drift test ───────────────────────────────────────────────────────


def test_missing_required_field() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


# ─── Artifact presence test ──────────────────────────────────────────────────


def test_missing_artifact() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.runbook_compliance") is None


def test_regression_binding_requires_explicit_affected_scope_and_distinct_revisions():
    manifest = AffectedSuiteManifest(
        test_ids=("tests/test_bug.py::test_boundary",),
        commands=(("python", "-m", "pytest", "tests/test_bug.py::test_boundary"),),
    )
    results = [EvaluationTestResult(test_id=manifest.test_ids[0], passed=True, output="1 passed")]
    unbound = bind_affected_regression_suite(
        manifest,
        base_sha="same-sha",
        candidate_sha="same-sha",
        base_results=results,
        candidate_results=results,
    )
    assert unbound.eligible is False
    assert unbound.reason_code == "BASE_CANDIDATE_BINDING_INVALID"
