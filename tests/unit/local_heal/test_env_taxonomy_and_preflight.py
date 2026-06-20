"""
Tests for env taxonomy, recipe registry, and repro pre-flight gate.
"""
import pytest
from nexus.services.local_heal.env_taxonomy import (
    EnvFailureTaxonomy, classify_env_failure, TAXONOMY_META
)
from nexus.services.local_heal.env_recipe_registry import EnvRecipeRegistry, EnvRecipe
from nexus.services.local_heal.repro_preflight import ReproPreflightDiagnosis, ReproPreflightResult


# ─── M1: Taxonomy Tests ───

def test_taxonomy_all_members_have_meta():
    """Every taxonomy member must have metadata."""
    for member in EnvFailureTaxonomy:
        assert member in TAXONOMY_META, f"Missing meta for {member}"
        meta = TAXONOMY_META[member]
        assert "agent_fixable" in meta
        assert "expected_stop_layer" in meta
        assert "claim_eligible" in meta


def test_taxonomy_agent_fixable_count():
    """At least half of taxonomy should be agent-fixable."""
    fixable = sum(1 for m in EnvFailureTaxonomy if TAXONOMY_META[m]["agent_fixable"])
    total = len(EnvFailureTaxonomy)
    assert fixable >= total / 2, f"Only {fixable}/{total} agent-fixable"


def test_classify_import_error():
    """ImportError → IMPORT_NOISE or DEPENDENCY_MISMATCH."""
    result = classify_env_failure("REPRO_ENVIRONMENT_FAILURE: ImportError", {}, {})
    assert result in (EnvFailureTaxonomy.IMPORT_NOISE, EnvFailureTaxonomy.DEPENDENCY_MISMATCH)


def test_classify_toolchain_missing():
    """BINARY_MISSING → TOOLCHAIN_MISSING."""
    result = classify_env_failure("BINARY_MISSING: gcc not found", {}, {})
    assert result == EnvFailureTaxonomy.TOOLCHAIN_MISSING


def test_classify_privilege():
    """PRIVILEGE → PRIVILEGE_REQUIRED."""
    result = classify_env_failure("PRIVILEGE_REQUIRED: need sudo", {}, {})
    assert result == EnvFailureTaxonomy.PRIVILEGE_REQUIRED


def test_classify_with_denoise():
    """env_denoise present → agent-fixable category."""
    result = classify_env_failure("ENV_BLOCKED", {}, {"numpy": "fix attempted"})
    assert result.value in [m.value for m in EnvFailureTaxonomy
                           if TAXONOMY_META[m]["agent_fixable"]]


def test_classify_default_is_fixable():
    """Unknown env failure defaults to DEPENDENCY_MISMATCH (agent-fixable)."""
    result = classify_env_failure("SOME_UNKNOWN_ERROR", {}, {})
    assert result == EnvFailureTaxonomy.DEPENDENCY_MISMATCH


# ─── M2: Recipe Registry Tests ───

def test_registry_has_builtin_recipes():
    """Registry should have at least 10 built-in recipes."""
    registry = EnvRecipeRegistry()
    recipes = registry.list_recipes()
    assert len(recipes) >= 10


def test_registry_match_numpy_drift():
    """Should match numpy API drift recipe."""
    registry = EnvRecipeRegistry()
    recipe = registry.match(["numpy.core.numeric", "np.bool"])
    assert recipe is not None
    assert recipe.id == "numpy_api_drift"
    assert "pip install" in recipe.allowed_actions[0]


def test_registry_match_import_error():
    """Should match missing dependency recipe."""
    registry = EnvRecipeRegistry()
    recipe = registry.match(["ImportError: No module named 'requests'"])
    assert recipe is not None
    assert recipe.id == "missing_dependency_install"


def test_registry_no_match():
    """Unknown signal → no match."""
    registry = EnvRecipeRegistry()
    recipe = registry.match(["completely_unknown_signal_xyz"])
    assert recipe is None


def test_registry_match_all():
    """match_all returns all matching recipes."""
    registry = EnvRecipeRegistry()
    recipes = registry.match_all(["numpy", "import"])
    assert len(recipes) >= 1
    ids = [r.id for r in recipes]
    assert "numpy_api_drift" in ids or "missing_dependency_install" in ids


def test_recipe_has_rollback():
    """Every recipe must have a rollback_hint."""
    registry = EnvRecipeRegistry()
    for recipe in registry.list_recipes():
        assert len(recipe.rollback_hint) > 0, f"Recipe {recipe.id} missing rollback_hint"


# ─── M3: Repro Pre-flight Tests ───

def _make_ctx(**overrides):
    from unittest.mock import MagicMock
    ctx = MagicMock()
    ctx.reproduced = overrides.get("reproduced", False)
    ctx.env_resolution = overrides.get("env_resolution", {"ready": True})
    ctx.env_denoise = overrides.get("env_denoise", {})
    ctx.failure_reason = overrides.get("failure_reason", "")
    ctx.repro_script = overrides.get("repro_script", "reproduce_bug.py")
    return ctx


def test_preflight_bug_reproduced_no_noise():
    """Bug reproduced, no noise → allow patch lane."""
    ctx = _make_ctx(reproduced=True)
    result = ReproPreflightDiagnosis.diagnose(ctx)
    assert result.bug_reproduced is True
    assert result.can_enter_patch_lane is True
    assert result.next_stop_layer == "localization"


def test_preflight_not_reproduced():
    """Bug not reproduced → stop at reprorunner."""
    ctx = _make_ctx(reproduced=False)
    result = ReproPreflightDiagnosis.diagnose(ctx)
    assert result.bug_reproduced is False
    assert result.can_enter_patch_lane is False
    assert result.next_stop_layer == "reprorunner"


def test_preflight_env_blocked():
    """Env blocked → stop at env_resolver."""
    ctx = _make_ctx(reproduced=False, env_resolution={"ready": False})
    result = ReproPreflightDiagnosis.diagnose(ctx)
    assert result.bug_reproduced is False
    assert result.can_enter_patch_lane is False
    assert result.next_stop_layer == "env_resolver"
    assert result.blocking_noise_present is True


def test_preflight_reproduced_with_noise_resolved():
    """Bug reproduced after noise was resolved → allow patch lane."""
    ctx = _make_ctx(reproduced=True, failure_reason="ENV_BLOCKED")
    result = ReproPreflightDiagnosis.diagnose(ctx)
    assert result.bug_reproduced is True
    assert result.can_enter_patch_lane is True
    assert result.next_stop_layer == "localization"
