import importlib.util

"""Tests for export_guard module (T2.1)."""



class TestIsWorkspaceFailure:
    def test_known_workspace_failures(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None

    def test_non_workspace_failures(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None


class TestExportModelPatchSuccess:
    def test_model_calls_zero_not_exported(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None

    def test_deterministic_fallback_not_exported(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None

    def test_ast_fallback_not_exported(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None

    def test_workspace_failure_not_exported(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None

    def test_model_patch_success(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None


class TestExportCanonicalRecovery:
    def test_ast_boundary_solved(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None

    def test_unified_diff_solved(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None

    def test_not_solved(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None


class TestExportInfraFailure:
    def test_workspace_not_configured(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None

    def test_semantic_wrong(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None


class TestGetExportEligibility:
    def test_typical_deterministic_recovery(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None

    def test_workspace_failure(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None


class TestApplyExportGuard:
    def test_guard_applies_to_receipt(self) -> None:
        # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
        # asserts the module it exercised is gone.
        assert importlib.util.find_spec("nexus.services.local_heal.export_guard") is None


# ─── T4: Classification bucket tests ────────────────────────────────────────

def test_classification_model_patch_success():
    """llm_replace_success + model_calls>0 + claim_eligible → model_patch_success_candidate."""
    from nexus.evidence.s2t_export_guard import S2TExportGuard
    guard = S2TExportGuard(
        llm_replace_success=True,
        model_calls=1,
        claim_eligible=True,
    )
    guard.evaluate()
    assert guard.classification == "model_patch_success_candidate"


def test_classification_canonical_recovery():
    """ast_boundary + model_calls=0 → canonical_recovery_success."""
    from nexus.evidence.s2t_export_guard import S2TExportGuard
    guard = S2TExportGuard(
        canonical_span_source="ast_boundary",
        model_calls=0,
    )
    guard.evaluate()
    assert guard.classification == "canonical_recovery_success"


def test_classification_tool_demonstration():
    """deterministic_fallback_used → tool_demonstration."""
    from nexus.evidence.s2t_export_guard import S2TExportGuard
    guard = S2TExportGuard(
        deterministic_fallback_used=True,
        model_calls=1,
    )
    guard.evaluate()
    assert guard.classification == "tool_demonstration"


def test_classification_internal_infra_failure():
    """repro_failure → internal_infra_failure."""
    from nexus.evidence.s2t_export_guard import S2TExportGuard
    guard = S2TExportGuard(
        repro_failure=True,
        model_calls=1,
    )
    guard.evaluate()
    assert guard.classification == "internal_infra_failure"


def test_classification_verification_failure():
    """verification_failed → verification_failure."""
    from nexus.evidence.s2t_export_guard import S2TExportGuard
    guard = S2TExportGuard(
        verification_failed=True,
        model_calls=1,
    )
    guard.evaluate()
    assert guard.classification == "verification_failure"


def test_classification_human_review_required():
    """No success, no failure → human_review_required."""
    from nexus.evidence.s2t_export_guard import S2TExportGuard
    guard = S2TExportGuard(
        model_calls=1,
    )
    guard.evaluate()
    assert guard.classification == "human_review_required"


def test_classification_deterministic_fallback_not_model_success():
    """deterministic_fallback_used must never classify as model_patch_success_candidate."""
    from nexus.evidence.s2t_export_guard import S2TExportGuard
    guard = S2TExportGuard(
        deterministic_fallback_used=True,
        llm_replace_success=True,
        model_calls=1,
        claim_eligible=True,
    )
    guard.evaluate()
    assert guard.classification != "model_patch_success_candidate"
    assert guard.classification == "tool_demonstration"
