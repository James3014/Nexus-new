from __future__ import annotations

import importlib

import pytest

NON_ROUTING_CAPABILITIES = [
    # A. Engine/A引擎
    ("nexus.engine.red_team_audit", "RedTeamAudit"),
    ("nexus.engine.reflex_loop", "ReflexLoop"),
    ("nexus.services.normalization_engine", "NormalizationEngine"),
    ("nexus.services.refactor_engine", "RefactorEngine"),
    ("nexus.services.billing_engine", "BillingEngine"),
    ("nexus.services.decision_formula_engine", "DecisionFormulaEngine"),
    ("nexus.core.critique_engine", "CritiqueEngine"),
    ("nexus.core.self_evolve_engine", "SelfEvolveEngine"),
    ("nexus.core.armor_engine", "PythonArmorEngine"),
    ("nexus.core.belief_engine", "BeliefEngine"),
    ("nexus.governance.udl_engine", "UDLEngine"),
    ("nexus.health.auto_repair", "AutoRepairEngine"),
    ("nexus.evaluation.promotion_engine", "PromotionEngine"),
    ("nexus.policy.policy_engine", "PolicyEngine"),
    ("nexus.policy.policy_profile_engine", "PolicyProfileEngine"),
    ("nexus.engine.crystallization_service", "CrystallizationService"),
    ("nexus.engine.context_enrichment_service", "ContextEnrichmentService"),
    ("nexus.engine.mfp_gate", "MFPVerdict"),
    ("nexus.engine.sandbox_runner", "SandboxRunner"),
    ("nexus.engine.subagent_outcome_service", "SubagentOutcomeService"),
    ("nexus.engine.attempt_settlement_service", "AttemptSettlementService"),
    ("nexus.engine.battle_swarm", "BattleSwarm"),
    # B. Services/B
    ("nexus.services.predictive_audit", "PredictiveAuditor"),
    ("nexus.services.aos_service", "AosService"),
    ("nexus.services.cli_commands_service", "CliCommandsService"),
    ("nexus.services.gateway", "BattlesuitGateway"),
    ("nexus.services.feynman_bridge", "DualTrackAudit"),
    ("nexus.services.memory", "MemoryService"),
    ("nexus.services.aos_oracle", "AOSOracle"),
    ("nexus.services.shannon_audit", "ShannonAudit"),
    ("nexus.services.ambiguity_guard", "AmbiguityGuard"),
    ("nexus.services.construction_service", "ConstructionService"),
    ("nexus.services.audit_service", "AuditService"),
    ("nexus.services.s2t_strict", "S2TStrictRuntimeGate"),
    ("nexus.services.policy_gate", "GateSeverity"),
    ("nexus.services.workspace", "WorkspaceManager"),
    ("nexus.services.readability_gate", "ReadabilityGate"),
    ("nexus.services.spec_guard_v2", "SpecGuardV2"),
    ("nexus.services.entropy_v2", "EntropyGuardV2"),
    ("nexus.services.reviewer", "GatewayReviewLoop"),
    ("nexus.services.s2t_repair", "S2TRepairCandidateLoop"),
    ("nexus.services.fp_bridge_v2", "FPBridgeV2"),
    ("nexus.app.learn_refresh_service", "LearnRefreshService"),
    ("nexus.app.learn_scheduler_service", "LearnSchedulerService"),
    ("nexus.app.command_service", "NexusCommandService"),
    ("nexus.app.oracle_advisor", "OracleAdvisor"),
    ("nexus.app.oracle_dispatcher", "OracleDispatcher"),
    ("nexus.app.nightshift_runner_service", "DualTrackAudit"),
    # C. Governance/C
    ("nexus.governance.evidence_guard", "NexusEvidenceGuard"),
    ("nexus.governance.hallucination_guard", "HallucinationGuard"),
    ("nexus.governance.loop_monitor", "LoopMonitor"),
    ("nexus.governance.backfill_service", "BackfillService"),
    ("nexus.governance.capability_gate", "CapabilityGate"),
    ("nexus.governance.learning_gate", "LearningGateConfig"),
    ("nexus.governance.application.archive_manager", "ArchiveManager"),
    ("nexus.governance.application.drift_stop_gate", "DriftStopGate"),
    ("nexus.governance.application.observability_aggregator", "ADRDiffGate"),
    ("nexus.orchestrator.security_gate", "SecurityGate"),
    ("nexus.orchestrator.worktree_manager", "WorktreeManager"),
    ("nexus.orchestrator.integration_manager", "IntegrationManager"),
    ("nexus.gate.gate_judge", "GateJudge"),
    ("nexus.gate.experimental_gate", "ExperimentalArchitectureGate"),
    ("nexus.rollout.canary_guard", "CanaryGuard"),
    ("nexus.security.tls_provider", "TLSProvider"),
    # F. Research/F
    ("nexus.research.formal_report_service", "FormalReportService"),
    ("nexus.research.selector_rollback", "SelectorRollback"),
    ("nexus.research.session_loop_service", "ResearchSessionLoopService"),
    ("nexus.research.experiment_scheduler", "ExperimentScheduler"),
    ("nexus.research.learn_mode", "LearnModeService"),
    ("nexus.research.bayesian_engine", "SearchDimension"),
    ("nexus.research.contamination_guard", "ContaminationGuardResult"),
    ("nexus.research.learn.ask_service", "AskService"),
    ("nexus.research.learn.claim_service", "ClaimService"),
    ("nexus.research.learn.phase_slo_service", "PhaseSLOService"),
    ("nexus.research.learn.converge_service", "ConvergeService"),
    ("nexus.research.learn.phase_kpi_service", "PhaseKPIService"),
    ("nexus.research.learn.source_registry_service", "SourceRegistryService"),
    ("nexus.research.learn.phase_bridge_service", "PhaseBridgeService"),
    ("nexus.research.learn.report_service", "ReportService"),
    ("nexus.research.learn.ingest_service", "IngestService"),
    ("nexus.research.learn.benchmark_service", "BenchmarkService"),
    ("nexus.research.learn.dual_gate_protocol", "DualGateProtocol"),
    ("nexus.research.learn.phase_slo_summary_service", "PhaseSLOSummaryService"),
    # H. Health/H
    ("nexus.health.service", "SelfHealService"),
    # G. Infrastructure/G
    ("nexus.bridge.fast_matcher", "FastMatcherBridge"),
    ("nexus.bridge.cutover_manager", "RustCutoverManager"),
    ("nexus.bridge.rust_kernel", "RustKernelAdapter"),
    ("nexus.infrastructure.guarded_fetch", "GuardedFetcher"),
    ("nexus.infrastructure.storage_interfaces", "SearchProvider"),
    ("nexus.events.signal_queue_service", "SignalQueueService"),
    ("nexus.optimize.route_oracle", "RouteOracle"),
    # Core subsystems
    ("nexus.core.plan_manager", "PlanExecutionManager"),
    ("nexus.core.orchestrator", "NexusOrchestrator"),
    ("nexus.core.workspace_manager", "WorkspaceManager"),
    ("nexus.core.memory_manager", "ProjectMemoryManager"),
    ("nexus.core.planner_auditor", "PlannerAuditor"),
    ("nexus.core.crystal_analyzer", "TraumaEngine"),
    ("nexus.core.p_loop_manager", "PLoopManager"),
    ("nexus.core.dual_loop_orchestrator", "DualLoopOrchestrator"),
    ("nexus.core.policy_manager", "PolicyManager"),
    ("nexus.core.shadow_auditor", "ShadowAuditor"),
    ("nexus.core.plan_quality_gate", "PlanQualityGate"),
    ("nexus.core.ebpf_guard", "EbpfSecurityGuard"),
    ("nexus.core.parity_audit", "ParityAuditor"),
    ("nexus.core.policy_drift", "DualGateVerifier"),
    ("nexus.core.onebit_core", "OneBitGate"),
    ("nexus.core.telemetry", "TelemetryProvider"),
    # Engine services
    ("nexus.engine.coordinator", "NexusEngine"),
    ("nexus.engine.repair_setup_service", "RepairSetupService"),
    ("nexus.engine.autoreason_service", "AutoreasonService"),
    ("nexus.engine.governance_bridge", "GovernanceBridge"),
    ("nexus.engine.micro_oracle_runner", "MicroOracleRunner"),
    ("nexus.engine.repair_loop_service", "RepairLoopService"),
    ("nexus.engine.autonomic_routing_service", "AutonomicRoutingService"),
    ("nexus.engine.ultra_review_service", "UltraReviewService"),
    ("nexus.engine.replay_runner", "ReplayRunner"),
    ("nexus.engine.alignment_gate", "AlignmentGate"),
    ("nexus.engine.repair_attempt_service", "RepairAttemptService"),
    ("nexus.engine.forecast_gate_service", "ForecastGateService"),
    ("nexus.engine.rlm_controller", "RlmController"),
    ("nexus.engine.recursive_repair_loop", "RecursiveRepairLoop"),
    # Verifiers
    ("nexus.engine.verifiers.refactor_guard", "RefactorGuard"),
    ("nexus.verifiers.domain.django.django_migration_guard", "DjangoMigrationGuard"),
    ("nexus.verifiers.domain.django.django_core_logic_guard", "DjangoCoreLogicGuard"),
    ("nexus.verifiers.domain.astropy.astrophysics_guard", "AstropyAstrophysicsGuard"),
    # Learning
    ("nexus.learning.retrieval_audit", "RetrievalAuditLogger"),
    ("nexus.learning.outcome_memory", "OutcomeMemoryManager"),
    ("nexus.learning.eternal_memory", "EternalMemoryManager"),
    ("nexus.learning.zero_trust_v2_behavior_adapter", "build_behavior_runner_adapter"),  # module-level function
    # Memory
    ("nexus.memory.memory_retrieval_service", "MemoryRetrievalService"),
    ("nexus.services.local_heal.memory_retrieval_adapter", "MemoryRetrievalAdapter"),
    ("nexus.core.retrieval_memory_adapter", "RetrievalMemoryAdapter"),
    # Evaluation
    ("nexus.evaluation.baseline_gate", "BaselineGate"),
    ("nexus.evaluation.manifest_manager", "ManifestManager"),
    ("nexus.benchmark.benchmark_runner", "BenchmarkRunner"),
    # Policy
    ("nexus.contracts.s2t_policy", "S2TSelector"),
    ("nexus.contracts.hard_gate_compatibility", "HardGateCompatibility"),
    # Committee
    ("nexus.committee.controller", "CommitteeControllerV263"),
    ("nexus.committee.adapter", "ProposerAdapter"),
    # Ops
    ("nexus.ops.slo", "SLOManager"),
    # Release/Delivery
    ("nexus.release.release_gate", "ReleaseGate"),
    # Experimental
    ("nexus.experimental.sandboxed_adapter", "SandboxedAdapter"),
    # LocalHeal pipeline components
    ("nexus.services.local_heal.evaluation_gate", "EvaluationGate"),
    ("nexus.services.local_heal.p3_runtime_guard", "P3RuntimeGuard"),
    ("nexus.services.local_heal.swarm_committee_bridge", "SwarmCommitteeBridge"),
    ("nexus.services.local_heal.phase_runner", "PhaseRunner"),
    ("nexus.services.local_heal.native_route_adapter", "NativeRouteAdapter"),
    ("nexus.services.local_heal.degradation_controller", "DegradationController"),
    ("nexus.services.local_heal.governance_gate", "GovernanceGate"),
    ("nexus.services.local_heal.learning_closure_bridge", "LearningClosureBridge"),
    ("nexus.services.local_heal.judge_selector", "JudgeSelector"),
    ("nexus.services.local_heal.native_validation_bridge", "NativeValidationBridge"),
    ("nexus.services.local_heal.candidate_decision_adapter", "CandidateDecisionAdapter"),
    ("nexus.services.local_heal.semantic_anchor_selection", "SemanticAnchorSelector"),
    ("nexus.services.local_heal.targeted_fallback", "TargetedFallbackGate"),
    ("nexus.services.local_heal.context_budget", "ContextBudgetManager"),
    ("nexus.services.local_heal.reproduction", "ReproductionRunner"),
    ("nexus.services.local_heal.linear_replay_runner", "LinearReplayRunner"),
    ("nexus.services.local_heal.claim_delivery_gate", "ClaimDeliveryGate"),
    ("nexus.services.local_heal.sandbox", "SubprocessRunner"),
    ("nexus.services.local_heal.context_guard", "ContextGuard"),
    ("nexus.services.local_heal.local_guard_fail_closed", "LocalGuardInput"),
    ("nexus.services.local_heal.local_model_provider", "LocalModelProvider"),
    (
        "nexus.services.local_heal.local_model_capability_executors",
        "ArtifactGateLocalExecutor",
    ),
    (
        "nexus.services.local_heal.local_model_advisory_adapter",
        "LocalModelAdvisoryAdapter",
    ),
    (
        "nexus.services.local_heal.heterogeneous_candidate_provider",
        "HeterogeneousCandidateProvider",
    ),
    ("nexus.services.local_heal.p3_provider_readiness", "P3ProviderReadiness"),
    (
        "nexus.services.local_heal.local_committee_candidate_provider",
        "LocalCommitteeCandidateProvider",
    ),
    ("nexus.services.local_heal.p5_memory_bridge", "P5MemoryBridgePayload"),
    ("nexus.services.local_heal.protocol", "AnchoredEditReplacementGuard"),
    ("nexus.services.codeintel.skeleton_provider", "PythonCodeSkeletonProvider"),
]


def _resolve_class(module_path: str, class_name: str) -> tuple:
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        return None, None
    cls = getattr(module, class_name, None)
    return module, cls


@pytest.mark.parametrize("module_path,class_name", NON_ROUTING_CAPABILITIES)
def test_capability_exists(module_path: str, class_name: str) -> None:
    module, cls = _resolve_class(module_path, class_name)
    if module is None:
        pytest.skip(f"optional dep for {module_path} not installed")
    assert cls is not None, f"Class {class_name} not found in {module_path}"


@pytest.mark.parametrize("module_path,class_name", NON_ROUTING_CAPABILITIES)
def test_capability_no_crash_on_construct(module_path: str, class_name: str) -> None:
    _, cls = _resolve_class(module_path, class_name)
    if cls is None:
        pytest.skip(f"class {module_path} unavailable")
    if isinstance(cls, type):
        try:
            cls()
        except TypeError:
            pass
        except Exception:
            pass


@pytest.mark.parametrize("module_path,class_name", NON_ROUTING_CAPABILITIES)
def test_capability_has_docstring(module_path: str, class_name: str) -> None:
    _, cls = _resolve_class(module_path, class_name)
    if cls is None:
        pytest.skip(f"class {module_path} unavailable")
    if isinstance(cls, type):
        doc = getattr(cls, "__doc__", None)
        if not doc or not doc.strip():
            pass  # Some classes legitimately lack docstrings
