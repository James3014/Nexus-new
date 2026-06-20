"""Tests for export_guard module (T2.1)."""

from nexus.services.local_heal.export_guard import (
    is_workspace_failure,
    should_export_as_model_patch_success,
    should_export_as_canonical_recovery_success,
    should_export_as_internal_infra_failure,
    get_export_eligibility,
    apply_export_guard,
    WORKSPACE_FAILURE_CLASSES,
)


class TestIsWorkspaceFailure:
    def test_known_workspace_failures(self):
        for fc in WORKSPACE_FAILURE_CLASSES:
            assert is_workspace_failure(fc), f"{fc} should be workspace failure"

    def test_non_workspace_failures(self):
        assert not is_workspace_failure("semantic_wrong")
        assert not is_workspace_failure("LOGIC_REGRESSION")
        assert not is_workspace_failure("VERIFICATION_FAILED")
        assert not is_workspace_failure("SOLVED")


class TestExportModelPatchSuccess:
    def test_model_calls_zero_not_exported(self):
        assert not should_export_as_model_patch_success(
            model_calls=0,
            model_patch_reward=0.0,
            deterministic_fallback_used=False,
            ast_fallback_used=False,
            canonical_span_source="unified_diff",
            failure_class="SOLVED",
        )

    def test_deterministic_fallback_not_exported(self):
        assert not should_export_as_model_patch_success(
            model_calls=1,
            model_patch_reward=1.0,
            deterministic_fallback_used=True,
            ast_fallback_used=False,
            canonical_span_source="unified_diff",
            failure_class="SOLVED",
        )

    def test_ast_fallback_not_exported(self):
        assert not should_export_as_model_patch_success(
            model_calls=1,
            model_patch_reward=1.0,
            deterministic_fallback_used=False,
            ast_fallback_used=True,
            canonical_span_source="ast_boundary",
            failure_class="SOLVED",
        )

    def test_workspace_failure_not_exported(self):
        assert not should_export_as_model_patch_success(
            model_calls=1,
            model_patch_reward=1.0,
            deterministic_fallback_used=False,
            ast_fallback_used=False,
            canonical_span_source="unified_diff",
            failure_class="workspace_not_configured",
        )

    def test_model_patch_success(self):
        assert should_export_as_model_patch_success(
            model_calls=1,
            model_patch_reward=1.0,
            deterministic_fallback_used=False,
            ast_fallback_used=False,
            canonical_span_source="unified_diff",
            failure_class="SOLVED",
        )


class TestExportCanonicalRecovery:
    def test_ast_boundary_solved(self):
        assert should_export_as_canonical_recovery_success(
            canonical_span_source="ast_boundary",
            model_calls=0,
            solved=True,
        )

    def test_unified_diff_solved(self):
        assert should_export_as_canonical_recovery_success(
            canonical_span_source="unified_diff",
            model_calls=0,
            solved=True,
        )

    def test_not_solved(self):
        assert not should_export_as_canonical_recovery_success(
            canonical_span_source="ast_boundary",
            model_calls=0,
            solved=False,
        )


class TestExportInfraFailure:
    def test_workspace_not_configured(self):
        assert should_export_as_internal_infra_failure(failure_class="workspace_not_configured")

    def test_semantic_wrong(self):
        assert not should_export_as_internal_infra_failure(failure_class="semantic_wrong")


class TestGetExportEligibility:
    def test_typical_deterministic_recovery(self):
        elig = get_export_eligibility(
            solved=True,
            model_calls=0,
            model_patch_reward=0.0,
            deterministic_fallback_used=True,
            ast_fallback_used=False,
            canonical_span_source="unified_diff",
            failure_class="SOLVED",
            claim_eligible=False,
        )
        assert elig["export_as_model_patch_success"] is False
        assert elig["export_as_canonical_recovery_success"] is True
        assert elig["export_as_internal_infra_failure"] is False
        assert elig["export_as_public_claim"] is False

    def test_workspace_failure(self):
        elig = get_export_eligibility(
            solved=False,
            model_calls=0,
            model_patch_reward=0.0,
            deterministic_fallback_used=False,
            ast_fallback_used=False,
            canonical_span_source="",
            failure_class="workspace_not_configured",
            claim_eligible=False,
        )
        assert elig["export_as_model_patch_success"] is False
        assert elig["export_as_internal_infra_failure"] is True
        assert elig["count_as_patcher_failure"] is False
        assert elig["count_as_model_failure"] is False


class TestApplyExportGuard:
    def test_guard_applies_to_receipt(self):
        receipt = {
            "claim_eligible": True,
            "public_claim_allowed": True,
            "telemetry": {
                "solved": True,
                "model_calls": 0,
                "model_patch_reward": 0.0,
                "deterministic_fallback_used": True,
                "ast_fallback_reward": "",
                "canonical_span_source": "unified_diff",
                "failure_class": "SOLVED",
            },
        }
        guarded = apply_export_guard(receipt)
        assert guarded["claim_eligible"] is False
        assert guarded["public_claim_allowed"] is False
        assert guarded["export_as_model_patch_success"] is False
        assert guarded["export_as_canonical_recovery_success"] is True
