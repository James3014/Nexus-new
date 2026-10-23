"""#2454 ratchet: every derived ``gate_passed`` site is migrated or baselined.

Modelled on tests/engine/test_gate_passed_site_inventory.py and
tests/core/test_registry_gate_passed_inventory.py.

* ``DECISION_PATHS`` lists the sites that make their pass decision through
  ``nexus.contracts.fail_closed.decide`` / ``decide_all``; an AST check proves it.
* A discovery scan over ``nexus/`` and ``scripts/ops/`` finds every function that
  sets ``gate_passed`` (keyword argument or dict key) from a non-constant
  expression. Each hit must be in ``DECISION_PATHS`` or in the frozen
  ``UNMIGRATED_BASELINE``. The baseline may only shrink.
"""

from __future__ import annotations

import ast
import functools
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("nexus", "scripts/ops")
HELPER_MODULE = "nexus.contracts.fail_closed"
HELPER_NAMES = frozenset({"decide", "decide_all"})

# "module:qualname" -> how the site decides. Only "HELPER" (fail_closed.decide/decide_all).
DECISION_PATHS: dict[str, str] = {
    "nexus.core.capability_executor_registry:_exec_committee": "HELPER",
}

# "module:qualname" -> reason. A derived site that is deliberately not a pass decision
# (e.g. a pure pass-through of an upstream receipt) may be registered here with a reason.
REGISTERED_EXEMPTIONS: dict[str, str] = {}

# Generated from origin/main afa134da1 (2026-10-17). May only shrink: migrate a site to
# nexus.contracts.fail_closed.decide, add it to DECISION_PATHS, and delete it here.
UNMIGRATED_BASELINE: frozenset[str] = frozenset({
    "nexus.app.nightshift_runner_service:AutoResearchNightShift._finalize_unified_runtime_receipt",
    "nexus.app.research_flow_service:run_auto_flow",
    "nexus.app.research_s2t_runtime:record_autoreason_s2t_trace",
    "nexus.app.research_semantic_runtime:augment_semantic_runtime_capabilities",
    "nexus.contracts.evidence_dataset:evidence_record_from_sf_smoke_case",
    "nexus.contracts.root_receipt:build_world_c_verifier_projection",
    "nexus.core.capability_executor_registry:_exec_acceptance_check",
    "nexus.core.capability_executor_registry:_exec_architecture_scout",
    "nexus.core.capability_executor_registry:_exec_artifact_gate",
    "nexus.core.capability_executor_registry:_exec_asi_constraint_extractor",
    "nexus.core.capability_executor_registry:_exec_autoreason",
    "nexus.core.capability_executor_registry:_exec_bdd_acceptance_skill",
    "nexus.core.capability_executor_registry:_exec_claim_gate",
    "nexus.core.capability_executor_registry:_exec_ddtree",
    "nexus.core.capability_executor_registry:_exec_drone",
    "nexus.core.capability_executor_registry:_exec_entropy_guard_v2",
    "nexus.core.capability_executor_registry:_exec_file_lock",
    "nexus.core.capability_executor_registry:_exec_forecast_gate",
    "nexus.core.capability_executor_registry:_exec_formal_report",
    "nexus.core.capability_executor_registry:_exec_harness_preflight_sensor",
    "nexus.core.capability_executor_registry:_exec_hyper_sprint",
    "nexus.core.capability_executor_registry:_exec_jit_validation",
    "nexus.core.capability_executor_registry:_exec_judge_panel",
    "nexus.core.capability_executor_registry:_exec_learn_mode",
    "nexus.core.capability_executor_registry:_exec_learn_phase_slo",
    "nexus.core.capability_executor_registry:_exec_learn_scheduler_service",
    "nexus.core.capability_executor_registry:_exec_mempalace",
    "nexus.core.capability_executor_registry:_exec_meta_opt",
    "nexus.core.capability_executor_registry:_exec_metabolism_resume",
    "nexus.core.capability_executor_registry:_exec_nightshift_runner_service",
    "nexus.core.capability_executor_registry:_exec_plan_quality_gate",
    "nexus.core.capability_executor_registry:_exec_pregate",
    "nexus.core.capability_executor_registry:_exec_registry_sync",
    "nexus.core.capability_executor_registry:_exec_research",
    "nexus.core.capability_executor_registry:_exec_sandbox_confined",
    "nexus.core.capability_executor_registry:_exec_sandbox_runner",
    "nexus.core.capability_executor_registry:_exec_swarm_multi_agent",
    "nexus.core.capability_executor_registry:_exec_xray",
    "nexus.core.capability_executor_registry:_make_receipt",
    "nexus.core.executor_controls:ExecutorControls.execute_plan.execute_single_cap",
    "nexus.core.metrics_aggregator:MetricsAggregator.aggregate_crystallize_payload",
    "nexus.core.router:SkillsRouter.route_candidates",
    "nexus.delivery.gate:evaluate_completion",
    "nexus.delivery.receipt:build_delivery_receipt",
    "nexus.engine.canonical_task_seam:_execution_learning_observer",
    "nexus.engine.capability_receipt_adapters:ASIConstraintExtractorReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:ArchitectureScoutReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:ArtifactGateReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:AutoreasonReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:BddAcceptanceSkillReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:BeliefReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:ClaimGateReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:CodeIntelReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:DDTreeReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:DeliveryGateReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:DroneReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:ExternalDocScoutReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:FormalReportReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:GenericCapabilityReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:HarnessPreflightSensorReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:HyperReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:IntentIntakeReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:JudgePanelReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:LanceDBReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:LocalHealReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:LocalModelExecutorReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:MemPalaceGateReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:MemoryReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:MsaRouterReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:NightshiftReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:RepairLoopReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:ResearchReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:SemanticFailureSensorReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:SemanticSearcherReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:StateTransitionReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:SwarmQuietMomentReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:SwarmReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:UltraReviewReceiptAdapter.build",
    "nexus.engine.capability_receipt_adapters:merge_capability_receipt",
    "nexus.engine.capability_receipt_parity:<module>",
    "nexus.engine.capability_receipt_parity:core_to_engine",
    "nexus.engine.capability_receipt_parity:engine_to_core",
    "nexus.engine.capability_receipt_parity:to_canonical_envelope",
    "nexus.engine.capability_receipts:_pending_receipt",
    "nexus.engine.capability_receipts:attested_receipt_dict",
    "nexus.engine.capability_receipts:evaluate_receipt_claim_boundary",
    "nexus.engine.pipeline_repair:PipelineRepairMixin._run_unified_advisor_online._disabled_online_invoker",
    "nexus.engine.pipeline_repair:PipelineRepairMixin._run_unified_advisor_online._v",
    "nexus.engine.pipeline_repair:PipelineRepairMixin._run_unified_advisor_online.learning_contract",
    "nexus.engine.pipeline_repair:PipelineRepairMixin._run_unified_advisor_online.online_invoker",
    "nexus.engine.pipeline_repair:PipelineRepairMixin._run_unified_advisor_online.response_contract",
    "nexus.engine.rlm_controller:build_bounded_rlm_orchestration_receipt",
    "nexus.engine.rlm_controller:build_rlm_decision_receipt",
    "nexus.engine.route_decision_adapter:RouteDecisionReceipt.to_dict",
    "nexus.engine.ultra_review_service:UltraReviewService._run",
    "nexus.learning.sf2_bounded_probe:evaluate_sf2_probe_row",
    "nexus.learning.skill_fit_closure:build_sf_flash_pair_live_report",
    "nexus.learning.skill_fit_closure:build_sf_live_pair_compare_report",
    "nexus.learning.skill_fit_closure:build_sf_paired_delta_report",
    "nexus.learning.skill_fit_closure:evaluate_bounded_probe_row",
    "nexus.research.architecture_scout:DistantScoutPlanner.plan",
    "nexus.research.contamination_guard:build_research_receipt",
    "nexus.research.day_shift_optimizer:DayShiftOptimizer._finalize_unified_runtime_receipts",
    "nexus.research.flow.capability_evidence:ultra_review_gate_evidence",
    "nexus.research.flow.unified_capability_projection:_compact_stage",
    "nexus.research.flow.unified_capability_projection:overlay_unified_capability_receipts",
    "nexus.research.flow.unified_capability_projection:reproject_receipt_base_claim_boundary",
    "nexus.research.local_assist_paired_experiment:run_arm_injected.verifier",
    "nexus.research.research_runtime_contracts:build_claim_probe",
    "nexus.research.sprint_service:_run_hyper_sprint_core._finalize_unified_receipt",
    "nexus.research.sprint_service:_visible_test_verdict",
    "nexus.services.capability_registry:build_local_model_executor_invoker.invoke",
    "nexus.services.capability_registry:build_real_executor_invoker._invoke_with",
    "nexus.services.continuous_learning:write_formal_lesson",
    "nexus.services.gateway:BattlesuitGateway.ask_unified.gateway_online_invoker",
    "nexus.services.local_heal.armor_artifact_storage:reconstruct_decision_from_receipt",
    "nexus.services.local_heal.hybrid_route_bridge:capability_payload_from_hybrid_route",
    "nexus.services.local_heal.local_armor_attempt_receipt:_build_committee_candidate_receipts",
    "nexus.services.local_heal.local_armor_attempt_receipt:_selected_capability_status",
    "nexus.services.local_heal.local_model_capability_context:CapabilityExecutionResult.to_receipt_dict",
    "nexus.services.local_heal.local_model_capability_executors:AutoreasonLocalExecutor.execute",
    "nexus.services.local_heal.local_model_capability_executors:DDTreeLocalExecutor.execute",
    "nexus.services.local_heal.local_model_capability_executors:LocalHealPipelineCapabilityExecutor.execute",
    "nexus.services.local_heal.local_model_executor:LocalModelExecutor._run_impl",
    "nexus.services.local_heal.orchestrator:HealOrchestrator._attach_live_full_loop_artifacts",
    "nexus.services.local_heal.receipt:build_repair_receipt",
    "nexus.services.local_heal.world_c_receipt:build_world_c_receipt",
    "nexus.services.online_nexus_context:build_codeintel_preflight_invoker.invoke",
    "nexus.services.online_nexus_context:build_plan_gated_postflight_invokers._make.invoke",
    "nexus.services.online_nexus_context:evaluate_postflight_gate",
    "nexus.services.online_nexus_context:make_with_nexus_online_invoker.invoke",
    "nexus.services.post_candidate_seam:_claim_boundary",
    "nexus.services.post_candidate_seam:seam_execution_evidence",
    "nexus.services.post_candidate_seam:stage_from_invocation",
    "nexus.services.product_capability_canary_helper:_run_canary_mainchain_cached._verifier",
    "nexus.services.s2t_strict:S2TStrictRuntimeGate.evaluate",
    "scripts.ops.build_heep_runtime_apply_gate:_chain_for_skill",
    "scripts.ops.build_heep_runtime_post_apply_smoke:_chain",
    "scripts.ops.build_sf_current_overlay_runtime_smoke:build_smoke",
    "scripts.ops.build_sf_runtime_receipt_smoke:_case",
    "scripts.ops.capability_invocation_index:build_arm_index",
    "scripts.ops.capability_invocation_index:merge_capability_cell",
    "scripts.ops.capability_wiring_audit:audit_executor_only",
    "scripts.ops.capability_wiring_audit:make_verifier.verifier",
    "scripts.ops.capability_wiring_audit:probe_file_lock",
    "scripts.ops.capability_wiring_audit:verdict_obs",
    "scripts.ops.crystal_factory:CrystalFactory.extract_patterns_via_ai._learn",
    "scripts.ops.crystal_factory:CrystalFactory.extract_patterns_via_ai._verify",
    "scripts.ops.nexus_acceptance_check:run_acceptance",
    "scripts.ops.run_skill_fit_ablation_matrix:_ablation_gate_row",
    "scripts.ops.unified_runtime_scenarios:_build_agy_online_invoker.invoke",
    "scripts.ops.unified_runtime_scenarios:_build_injected_online_invoker.invoke",
    "scripts.ops.unified_runtime_scenarios:_capability_edge_summary",
    "scripts.ops.unified_runtime_scenarios:_learning_callback.learn",
    "scripts.ops.unified_runtime_scenarios:_verifier.verify",
    "scripts.ops.verify_agent_skill_lifecycle_overlay:verify",
    "scripts.ops.verify_reasoning_failure_chain:<module>",
    "scripts.ops.verify_reasoning_full_chain:<module>",
    "scripts.ops:_run_anti_drift_gate",
})
# Ratchet ceiling: lower it whenever a site is migrated; never raise it.
UNMIGRATED_BASELINE_MAX = 160


def _module_name(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_derived(value: ast.expr) -> bool:
    return not isinstance(value, ast.Constant)


class _SiteVisitor(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.stack: list[str] = []
        self.hits: set[str] = set()

    def _scoped(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _scoped
    visit_AsyncFunctionDef = _scoped
    visit_ClassDef = _scoped

    def _record(self) -> None:
        qualname = ".".join(self.stack) if self.stack else "<module>"
        self.hits.add(f"{self.module}:{qualname}")

    def visit_keyword(self, node: ast.keyword) -> None:
        if node.arg == "gate_passed" and _is_derived(node.value):
            self._record()
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "gate_passed" and _is_derived(value):
                self._record()
        self.generic_visit(node)


def _source_files() -> Iterator[Path]:
    for root in SCAN_ROOTS:
        yield from sorted((REPO_ROOT / root).rglob("*.py"))


def discover_derived_gate_sites() -> frozenset[str]:
    return _discover_cached()


@functools.cache
def _discover_cached() -> frozenset[str]:
    hits: set[str] = set()
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        if "gate_passed" not in text:
            continue
        visitor = _SiteVisitor(_module_name(path))
        visitor.visit(ast.parse(text, filename=str(path)))
        hits |= visitor.hits
    return frozenset(hits)


def _find_function(tree: ast.Module, qualname: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    scope: list[ast.stmt] = list(tree.body)
    parts = qualname.split(".")
    for index, part in enumerate(parts):
        for node in scope:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (
                node.name == part
            ):
                if index == len(parts) - 1:
                    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)), qualname
                    return node
                scope = list(node.body)
                break
        else:
            raise AssertionError(f"{qualname}: not found")
    raise AssertionError(f"{qualname}: not found")


def _helper_aliases(tree: ast.Module) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == HELPER_MODULE:
            aliases |= {a.asname or a.name for a in node.names if a.name in HELPER_NAMES}
    return aliases


def test_decision_paths_call_the_fail_closed_helper() -> None:
    for site, kind in sorted(DECISION_PATHS.items()):
        assert kind == "HELPER", site
        module, qualname = site.split(":")
        path = REPO_ROOT / (module.replace(".", "/") + ".py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _helper_aliases(tree)
        assert aliases, f"{site}: {HELPER_MODULE}.decide/decide_all is not imported"
        func = _find_function(tree, qualname)
        called = {
            node.func.id
            for node in ast.walk(func)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert called & aliases, f"{site}: does not call {sorted(aliases)}"


def test_scan_finds_known_sites() -> None:
    hits = discover_derived_gate_sites()
    assert "nexus.core.capability_executor_registry:_exec_committee" in hits, (
        "discovery scan found nothing; it is broken"
    )
    assert len(hits) > 10


def test_every_derived_gate_site_is_migrated_or_baselined() -> None:
    hits = discover_derived_gate_sites()
    registered = set(DECISION_PATHS) | set(REGISTERED_EXEMPTIONS)
    unregistered = sorted(hits - registered - UNMIGRATED_BASELINE)
    assert unregistered == [], (
        "New gate_passed site(s) derived from a non-constant expression: "
        f"{unregistered}. Decide the pass with nexus.contracts.fail_closed.decide "
        "(or decide_all) and add the site to DECISION_PATHS in "
        "tests/contracts/test_fail_closed_inventory.py, or register it in "
        "REGISTERED_EXEMPTIONS with a reason. "
        "Do not add new entries to UNMIGRATED_BASELINE (#2454)."
    )


def test_baseline_only_shrinks() -> None:
    """Every baseline entry must still exist; a migrated or removed site must be deleted."""
    hits = discover_derived_gate_sites()
    stale = sorted(UNMIGRATED_BASELINE - hits)
    assert stale == [], f"remove these from UNMIGRATED_BASELINE (no longer derived sites): {stale}"
    assert not (UNMIGRATED_BASELINE & set(DECISION_PATHS))
    assert not (UNMIGRATED_BASELINE & set(REGISTERED_EXEMPTIONS))
    assert all(isinstance(r, str) and r.strip() for r in REGISTERED_EXEMPTIONS.values())
    assert len(UNMIGRATED_BASELINE) <= UNMIGRATED_BASELINE_MAX, (
        "UNMIGRATED_BASELINE grew; it may only shrink. Use nexus.contracts.fail_closed.decide."
    )
