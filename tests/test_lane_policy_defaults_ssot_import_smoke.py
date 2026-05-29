from __future__ import annotations

def test_lane_policy_defaults_ssot_import_smoke():
    """M1 Smoke: Verify engine and bench import the identical core defaults.

    This focused smoke test ensures the single source of truth (SSOT) of lane policy controls
    is successfully loaded at both layers without circular dependency or path anomalies.
    """
    from nexus.core.lane_policy_defaults import LANE_POLICY_DEFAULTS as core_defaults
    from nexus.engine.learning_policy_loader import LANE_POLICY_DEFAULTS as loader_defaults
    from scripts.bench.route_execution_policy import LANE_POLICY_DEFAULTS as runner_defaults

    # Ensure memory address identity to enforce strict SSOT
    assert core_defaults is loader_defaults, "Engine loader defaults drifts from core"
    assert core_defaults is runner_defaults, "Runner policy defaults drifts from core"

    # Enforce core structural integrity checks
    assert "hidden_bugfix_supervised" in core_defaults
    assert core_defaults["hidden_bugfix_supervised"].get("allow_pre_model_deterministic_rescue") is True

    assert "governance_hardened" in core_defaults
    assert core_defaults["governance_hardened"].get("skip_llm_baseline") is True

    assert "context_sync_capped" in core_defaults
    assert core_defaults["context_sync_capped"].get("supervised_bare_first") is True
