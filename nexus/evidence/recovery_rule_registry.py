"""
Recovery Rule Registry: Records deterministic/canonical recovery rules
with rule id, scope, trigger, reward attribution, and export eligibility.

T2.1 Known Rules:
- AST_SYMBOL_FIX: AST boundary extraction fixed SEARCH_MISMATCH
- REMOVE_BLOCK: Deterministic block removal fixed verification failure
- AST_BOUNDARY_EXTRACT: AST boundary extraction for canonical span
- locked_search_reuse: Reused locked SEARCH span from previous attempt
- unified_diff_reuse: Reused unified_diff from previous attempt
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import json
from pathlib import Path


@dataclass
class RecoveryRule:
    """A single recovery rule definition."""
    rule_id: str
    rule_type: str  # deterministic_fallback | canonical_span_recovery | semantic_recovery | locked_search_reuse | unified_diff_reuse | repro_recovery | workspace_recovery
    description: str = ""
    trigger_condition: str = ""
    allowed_projects: List[str] = field(default_factory=list)
    allowed_failure_classes: List[str] = field(default_factory=list)
    canonical_span_source: str = ""
    model_calls_required: int = 0
    model_patch_reward: float = 0.0
    deterministic_fallback_reward: float = 0.0
    ast_fallback_reward: float = 0.0
    repro_recovery_reward: float = 0.0
    workspace_recovery_reward: float = 0.0
    export_as_model_patch_success: bool = False
    export_as_canonical_recovery_success: bool = False
    export_as_tool_demonstration: bool = True
    export_as_internal_infra_failure: bool = False
    export_as_public_claim: bool = False
    count_as_model_failure: bool = False
    count_as_patcher_failure: bool = True
    requires_human_review_before_training: bool = True

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "description": self.description,
            "trigger_condition": self.trigger_condition,
            "allowed_projects": self.allowed_projects,
            "allowed_failure_classes": self.allowed_failure_classes,
            "canonical_span_source": self.canonical_span_source,
            "model_calls_required": self.model_calls_required,
            "model_patch_reward": self.model_patch_reward,
            "deterministic_fallback_reward": self.deterministic_fallback_reward,
            "ast_fallback_reward": self.ast_fallback_reward,
            "export_as_model_patch_success": self.export_as_model_patch_success,
            "export_as_canonical_recovery_success": self.export_as_canonical_recovery_success,
            "export_as_tool_demonstration": self.export_as_tool_demonstration,
            "export_as_public_claim": self.export_as_public_claim,
            "requires_human_review_before_training": self.requires_human_review_before_training,
        }


# T2.1 Known Recovery Rules
RECOVERY_RULES = {
    "AST_SYMBOL_FIX": RecoveryRule(
        rule_id="AST_SYMBOL_FIX",
        rule_type="canonical_span_recovery",
        description="AST boundary extraction fixed SEARCH_MISMATCH by finding function/class by name",
        trigger_condition="SEARCH_MISMATCH + ast_boundary canonical span found",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["patch_mismatch", "SEARCH_MISMATCH"],
        canonical_span_source="ast_boundary",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=1.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=True,
        export_as_tool_demonstration=True,
        export_as_public_claim=False,
        requires_human_review_before_training=True,
    ),
    "REMOVE_BLOCK": RecoveryRule(
        rule_id="REMOVE_BLOCK",
        rule_type="deterministic_fallback",
        description="Deterministic block removal fixed verification failure (e.g., NdarrayMixin auto-transform)",
        trigger_condition="verification_failed + deterministic block removal applied",
        allowed_projects=["astropy"],
        allowed_failure_classes=["semantic_wrong", "verification_failed"],
        canonical_span_source="unified_diff",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=1.0,
        ast_fallback_reward=0.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=True,
        export_as_public_claim=False,
        requires_human_review_before_training=True,
    ),
    "AST_BOUNDARY_EXTRACT": RecoveryRule(
        rule_id="AST_BOUNDARY_EXTRACT",
        rule_type="canonical_span_recovery",
        description="AST boundary extraction for canonical span when line-by-line matching fails",
        trigger_condition="canonical span lookup fails + AST finds target symbol",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["patch_mismatch", "SEARCH_MISMATCH", "NO_BLOCKS_FOUND"],
        canonical_span_source="ast_boundary",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=1.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=True,
        export_as_tool_demonstration=True,
        export_as_public_claim=False,
        requires_human_review_before_training=True,
    ),
    "locked_search_reuse": RecoveryRule(
        rule_id="locked_search_reuse",
        rule_type="locked_search_reuse",
        description="Reused locked SEARCH span from previous patch attempt",
        trigger_condition="SEARCH_MISMATCH + locked SEARCH reused from prior attempt",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["patch_mismatch", "SEARCH_MISMATCH"],
        canonical_span_source="locked_search",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=True,
        export_as_public_claim=False,
        requires_human_review_before_training=True,
    ),
    "unified_diff_reuse": RecoveryRule(
        rule_id="unified_diff_reuse",
        rule_type="unified_diff_reuse",
        description="Reused unified_diff from previous patch attempt",
        trigger_condition="verification_failed + unified_diff reused",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["semantic_wrong", "verification_failed"],
        canonical_span_source="unified_diff",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=True,
        export_as_public_claim=False,
        requires_human_review_before_training=True,
    ),
    "verification_guided_retry": RecoveryRule(
        rule_id="verification_guided_retry",
        rule_type="semantic_recovery",
        description="Verification-guided retry with locked SEARCH and rewritten REPLACE",
        trigger_condition="verification_failed + semantic retry with locked SEARCH",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["semantic_wrong", "verification_failed"],
        canonical_span_source="locked_search",
        model_calls_required=1,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=True,
        export_as_public_claim=False,
        requires_human_review_before_training=True,
    ),
    "repro_env_noise": RecoveryRule(
        rule_id="repro_env_noise",
        rule_type="repro_recovery",
        description="Repro failure due to environment noise (not a real bug)",
        trigger_condition="repro_failure + env_noise subclass",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["repro_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "repro_bug_not_reproduced": RecoveryRule(
        rule_id="repro_bug_not_reproduced",
        rule_type="repro_recovery",
        description="Repro failure because bug was not actually reproduced",
        trigger_condition="repro_failure + bug_not_reproduced subclass",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["repro_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "workspace_config_fix": RecoveryRule(
        rule_id="workspace_config_fix",
        rule_type="workspace_recovery",
        description="Workspace configuration fixed (Python version, dependencies, PYTHONPATH)",
        trigger_condition="workspace_failure + config_fix applied",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["workspace_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "repro_script_fix": RecoveryRule(
        rule_id="repro_script_fix",
        rule_type="repro_recovery",
        description="Repro script issue fixed (wrong expected behavior, missing import, wrong symbol)",
        trigger_condition="repro_script_issue + fix applied",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["repro_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        repro_recovery_reward=1.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "unstable_reproduction_guard": RecoveryRule(
        rule_id="unstable_reproduction_guard",
        rule_type="repro_guard",
        description="Unstable reproduction detected — cannot count as model/patcher failure",
        trigger_condition="unstable_reproduction detected",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["repro_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "test_harness_error_guard": RecoveryRule(
        rule_id="test_harness_error_guard",
        rule_type="test_harness_guard",
        description="Test harness error detected — not a model/patcher failure",
        trigger_condition="test_harness_error detected",
        allowed_projects=["astropy", "django", "sympy", "flask", "requests"],
        allowed_failure_classes=["repro_failure", "verification_failed"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "repro_script_wrong_expected_behavior_fix": RecoveryRule(
        rule_id="repro_script_wrong_expected_behavior_fix",
        rule_type="repro_recovery",
        description="Repro script fixed: wrong expected behavior corrected",
        trigger_condition="repro_script_wrong_expected_behavior + fix applied",
        allowed_projects=["sympy"],
        allowed_failure_classes=["repro_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        repro_recovery_reward=1.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "dependency_missing_fix": RecoveryRule(
        rule_id="dependency_missing_fix",
        rule_type="workspace_recovery",
        description="Missing dependency installed (e.g., beautifulsoup4, lxml)",
        trigger_condition="dependency_missing + install applied",
        allowed_projects=["astropy", "django", "sympy"],
        allowed_failure_classes=["workspace_failure", "dependency_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        workspace_recovery_reward=1.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "parser_dependency_missing_fix": RecoveryRule(
        rule_id="parser_dependency_missing_fix",
        rule_type="workspace_recovery",
        description="Parser dependency missing and installed",
        trigger_condition="parser_dependency_missing + install applied",
        allowed_projects=["astropy", "django", "sympy"],
        allowed_failure_classes=["workspace_failure", "dependency_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        workspace_recovery_reward=1.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "astropy_html_dependency_fix": RecoveryRule(
        rule_id="astropy_html_dependency_fix",
        rule_type="workspace_recovery",
        description="Astropy HTML parsing dependency (bs4, lxml) installed",
        trigger_condition="astropy_html_dependency_missing + install applied",
        allowed_projects=["astropy"],
        allowed_failure_classes=["workspace_failure", "dependency_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        workspace_recovery_reward=1.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "sympy_python39_workspace_fix": RecoveryRule(
        rule_id="sympy_python39_workspace_fix",
        rule_type="workspace_recovery",
        description="Sympy workspace configured with Python 3.9 for collections.Mapping compatibility",
        trigger_condition="sympy_workspace + python39 configured",
        allowed_projects=["sympy"],
        allowed_failure_classes=["workspace_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        workspace_recovery_reward=1.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
    "django_workspace_validation": RecoveryRule(
        rule_id="django_workspace_validation",
        rule_type="workspace_recovery",
        description="Django workspace validated and configured",
        trigger_condition="django_workspace + validation passed",
        allowed_projects=["django"],
        allowed_failure_classes=["workspace_failure"],
        canonical_span_source="",
        model_calls_required=0,
        model_patch_reward=0.0,
        deterministic_fallback_reward=0.0,
        ast_fallback_reward=0.0,
        workspace_recovery_reward=1.0,
        export_as_model_patch_success=False,
        export_as_canonical_recovery_success=False,
        export_as_tool_demonstration=False,
        export_as_internal_infra_failure=True,
        export_as_public_claim=False,
        count_as_model_failure=False,
        count_as_patcher_failure=False,
        requires_human_review_before_training=True,
    ),
}


class RecoveryRuleRegistry:
    """Registry for recovery rules."""

    def __init__(self):
        self.rules = dict(RECOVERY_RULES)

    def get_rule(self, rule_id: str) -> Optional[RecoveryRule]:
        return self.rules.get(rule_id)

    def list_rules(self) -> List[RecoveryRule]:
        return list(self.rules.values())

    def to_dict(self) -> dict:
        return {rule_id: rule.to_dict() for rule_id, rule in self.rules.items()}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "RecoveryRuleRegistry":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            registry = cls()
            for rule_id, rule_data in data.items():
                registry.rules[rule_id] = RecoveryRule(**rule_data)
            return registry
        except Exception:
            return cls()


def get_recovery_rule(rule_id: str) -> Optional[RecoveryRule]:
    """Convenience function to get a recovery rule."""
    return RECOVERY_RULES.get(rule_id)
