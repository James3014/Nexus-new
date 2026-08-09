"""Curated, authority-bound Nexus Golden Behavior Corpus.

This module is data, not a second architecture or behavior authority.  Each
case points back to current source/contracts or to a GitHub decision/evidence
frontier.  Findings record gaps without changing product behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    title: str
    classification: str
    scenario: str
    expected_behavior: str
    authority_sources: tuple[str, ...]
    automated_tests: tuple[str, ...] = ()
    finding_probe: str | None = None
    status: str = "covered"
    finding_id: str | None = None


def _c(
    case_id: str,
    title: str,
    classification: str,
    scenario: str,
    expected_behavior: str,
    authority_sources: tuple[str, ...],
    automated_tests: tuple[str, ...] = (),
    *,
    finding_probe: str | None = None,
    status: str = "covered",
    finding_id: str | None = None,
) -> GoldenCase:
    return GoldenCase(
        case_id,
        title,
        classification,
        scenario,
        expected_behavior,
        authority_sources,
        automated_tests,
        finding_probe,
        status,
        finding_id,
    )


ROUTE = (
    "AGENTS.md#Authority invariants",
    "nexus/engine/canonical_execution.py",
    "nexus/contracts/canonical_execution.py",
    "docs/adr/0001-selection-search-split.md",
)
HYBRID = ("AGENTS.md#Authority invariants", "nexus/contracts/hybrid_route.py")
WORKFORCE = ("docs/agents/WORKFORCE_EXECUTION_OVERLAY.md", "nexus/contracts/workforce_admission.py")
LIFECYCLE = (
    "docs/agents/TASK_EXECUTION_CONTRACT.md",
    "nexus/orchestrator/self_hosted_task_service.py",
    "docs/adr/0004-feedback-retry-separation.md",
    "docs/adr/0014-promotion-receipt-spec.md",
)
GATEWAY = (
    "nexus/orchestrator/unified_mcp_gateway.py",
    "https://github.com/James3014/Nexus-new/issues/12",
)
CLAIM = (
    "docs/agents/CLAIM_AND_RECEIPT_OVERLAY.md",
    "nexus/contracts/claim_evidence_read_model.py",
    "docs/adr/0008-evidence-driven-promotion.md",
)
REPO_GATE = (
    "AGENTS.md#Governed task-card and artifact governance",
    "nexus/orchestrator/repository_contract_gate.py",
    "docs/adr/0015-v28-architecture-freeze.md",
)
LEARNING = ("docs/agents/LEARNING_WRITEBACK_OVERLAY.md", "nexus/contracts/learning_experience.py")


CASES: tuple[GoldenCase, ...] = (
    _c(
        "GB-001",
        "Plan exactly once",
        "invariant",
        "normal",
        "Canonical planning calls CapabilityPlanner exactly once and only projects its decision.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_canonical_task_context_plans_once_and_projects_only_planner_decision",
        ),
    ),
    _c(
        "GB-002",
        "Facts are not route authority",
        "security",
        "authority_conflict",
        "Caller-supplied code-target facts may inform planning but cannot become route authority.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_canonical_context_allows_code_target_facts_but_not_target_authority",
        ),
    ),
    _c(
        "GB-003",
        "Formal route receipts remain evidence",
        "compatibility",
        "normal",
        "A formal route receipt may be carried as evidence without replacing CapabilityPlanner.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_canonical_context_allows_formal_route_receipt_evidence",
        ),
    ),
    _c(
        "GB-004",
        "Planning bundle binds exact plan",
        "invariant",
        "idempotency",
        "A canonical planning bundle binds one exact plan and does not silently replan.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_canonical_planning_bundle_binds_the_exact_plan_without_replanning",
        ),
    ),
    _c(
        "GB-005",
        "Planning bundle cannot be rebound",
        "security",
        "malformed_input",
        "Mutating or rebinding a planning bundle to another plan fails closed.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_canonical_planning_bundle_cannot_be_mutated_or_rebound_to_another_plan",
        ),
    ),
    _c(
        "GB-006",
        "Execution channels require workforce demand",
        "invariant",
        "boundary",
        "Available execution channels require explicit workforce demands in the canonical context.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_canonical_context_requires_workforce_demands_for_available_execution_channels",
        ),
    ),
    _c(
        "GB-007",
        "Replan requires explicit authorization",
        "security",
        "authority_conflict",
        "A fresh plan may be created only through explicit replan authorization.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_canonical_replan_builds_one_fresh_bundle_from_explicit_authorization",
        ),
    ),
    _c(
        "GB-008",
        "Wire tamper fails closed",
        "security",
        "malformed_input",
        "Planning-bundle wire round trips reject tampered identity or content.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_canonical_planning_bundle_wire_round_trip_rejects_tamper",
        ),
    ),
    _c(
        "GB-009",
        "Alternate planner injection is rejected",
        "security",
        "authority_conflict",
        "A caller cannot inject an alternate planner authority.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_caller_cannot_inject_an_alternate_planner_authority",
        ),
    ),
    _c(
        "GB-010",
        "Capability projection tamper is rejected",
        "security",
        "malformed_input",
        "Tampering with projected selected capabilities cannot change canonical route truth.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_projection_tamper_cannot_change_selected_capabilities",
        ),
    ),
    _c(
        "GB-011",
        "Constraint projection tamper is rejected",
        "security",
        "malformed_input",
        "Tampering with projected constraints cannot change the canonical plan.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_projection_tamper_cannot_change_constraints",
        ),
    ),
    _c(
        "GB-012",
        "Nested authority override is rejected",
        "security",
        "authority_conflict",
        "Nested route or execution-authority overrides fail with a stable contract error.",
        ROUTE,
        (
            "tests/contracts/test_canonical_execution.py::test_context_rejects_nested_route_and_execution_authority_overrides[route_features-execution_lane]",
            "tests/contracts/test_canonical_execution.py::test_context_rejects_nested_route_and_execution_authority_overrides[pillars-provider]",
            "tests/contracts/test_canonical_execution.py::test_context_rejects_nested_route_and_execution_authority_overrides[codeintel-model]",
            "tests/contracts/test_canonical_execution.py::test_context_rejects_nested_route_and_execution_authority_overrides[phase_trace-target_worktree]",
            "tests/contracts/test_canonical_execution.py::test_context_rejects_nested_route_and_execution_authority_overrides[budget-route_override]",
            "tests/contracts/test_canonical_execution.py::test_context_rejects_nested_route_and_execution_authority_overrides[budget-lifecycle_state]",
            "tests/contracts/test_canonical_execution.py::test_context_rejects_nested_route_and_execution_authority_overrides[budget-world]",
            "tests/contracts/test_canonical_execution.py::test_context_rejects_nested_route_and_execution_authority_overrides[budget-worker]",
        ),
    ),
    _c(
        "GB-013",
        "Hybrid route defaults are non-claiming",
        "invariant",
        "normal",
        "Default hybrid decisions are trace-only, candidate-isolated, not production-ready, and not public-claim eligible.",
        HYBRID,
        ("tests/contracts/test_hybrid_route_contract.py::test_hybrid_route_default_values",),
    ),
    _c(
        "GB-014",
        "Hybrid payload round trip",
        "compatibility",
        "normal",
        "Hybrid route payloads round-trip without changing enum semantics.",
        HYBRID,
        ("tests/contracts/test_hybrid_route_contract.py::test_to_dict_round_trip",),
    ),
    _c(
        "GB-015",
        "Invalid verifier result rejected",
        "regression",
        "malformed_input",
        "An unknown verifier-result value fails closed.",
        HYBRID,
        ("tests/contracts/test_hybrid_route_contract.py::test_invalid_verifier_result_fails",),
    ),
    _c(
        "GB-016",
        "Hybrid decision cannot self-declare production",
        "security",
        "authority_conflict",
        "Hybrid route construction rejects production_ready=true.",
        HYBRID,
        ("tests/contracts/test_hybrid_route_contract.py::test_production_ready_true_fails",),
    ),
    _c(
        "GB-017",
        "Adapter output is not route truth",
        "security",
        "authority_conflict",
        "Adapter output cannot declare itself route authority.",
        HYBRID,
        (
            "tests/contracts/test_hybrid_route_contract.py::test_adapter_output_is_route_truth_true_fails",
        ),
    ),
    _c(
        "GB-018",
        "Local execution binds selected and applied hashes",
        "invariant",
        "partial_state",
        "Local-only execution is valid only when selected-candidate and applied-patch hashes match.",
        HYBRID,
        (
            "tests/contracts/test_hybrid_route_contract.py::test_local_only_executed_requires_hash_match",
        ),
    ),
    _c(
        "GB-019",
        "Advisory guard cannot block delivery",
        "compatibility",
        "authority_conflict",
        "An advisory local guard cannot become a delivery blocker or second verifier.",
        HYBRID,
        (
            "tests/contracts/test_hybrid_route_contract.py::test_advisory_guard_cannot_block_delivery_yet",
        ),
    ),
    _c(
        "GB-020",
        "Hybrid decision cannot unlock public claims",
        "security",
        "authority_conflict",
        "Hybrid route construction rejects public_claim_allowed=true.",
        HYBRID,
        ("tests/contracts/test_hybrid_route_contract.py::test_public_claim_allowed_true_fails",),
    ),
    _c(
        "GB-021",
        "Admission decision vocabulary is stable",
        "compatibility",
        "normal",
        "Workforce admission decision enum values remain deterministic and stable.",
        WORKFORCE,
        (
            "tests/contracts/test_workforce_admission_contract.py::test_admission_decision_enum_values",
        ),
    ),
    _c(
        "GB-022",
        "Autonomy parsing and ordering is deterministic",
        "compatibility",
        "malformed_input",
        "Autonomy levels parse and order deterministically.",
        WORKFORCE,
        (
            "tests/contracts/test_workforce_admission_contract.py::test_autonomy_level_deterministic_parsing_and_ordering",
        ),
    ),
    _c(
        "GB-023",
        "Admission request is immutable",
        "security",
        "malformed_input",
        "Serialized workforce admission requests cannot be mutated after binding.",
        WORKFORCE,
        (
            "tests/contracts/test_workforce_admission_contract.py::test_workforce_admission_request_serialization_and_immutability",
        ),
    ),
    _c(
        "GB-024",
        "Worker identity is immutable",
        "security",
        "authority_conflict",
        "Serialized worker/provider/model identity cannot be rewritten after admission.",
        WORKFORCE,
        (
            "tests/contracts/test_workforce_admission_contract.py::test_workforce_worker_serialization_and_immutability",
        ),
    ),
    _c(
        "GB-025",
        "Admission decision schema is stable",
        "compatibility",
        "normal",
        "Admission decisions preserve their schema and serialization contract.",
        WORKFORCE,
        (
            "tests/contracts/test_workforce_admission_contract.py::test_workforce_admission_decision_schema_and_serialization",
        ),
    ),
    _c(
        "GB-026",
        "Submit is idempotent",
        "invariant",
        "idempotency",
        "Resubmitting the same exact task contract returns the same durable task state.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_submit_persists_idempotent_task_state",
        ),
    ),
    _c(
        "GB-027",
        "Submitted time binds initial history",
        "regression",
        "normal",
        "submitted_at equals the initial submitted history event.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_submitted_at_matches_initial_submitted_history_entry",
        ),
    ),
    _c(
        "GB-028",
        "Submitted time survives resubmission",
        "invariant",
        "idempotency",
        "Idempotent resubmission cannot rewrite submitted_at.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_submitted_at_is_stable_across_idempotent_resubmission",
        ),
    ),
    _c(
        "GB-029",
        "Raw prompts and unknown workers are rejected",
        "security",
        "malformed_input",
        "Governed submission rejects raw prompts and unknown worker identities before execution.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_submit_rejects_raw_prompt_and_unknown_worker",
        ),
    ),
    _c(
        "GB-030",
        "Approval is hash-bound and non-integrating",
        "security",
        "authority_conflict",
        "Approval binds exact evidence hashes and does not itself merge or integrate.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_approval_is_hash_bound_and_does_not_merge",
        ),
    ),
    _c(
        "GB-031",
        "Approval tamper fails closed",
        "security",
        "stale_state",
        "A marked-authority approval with tampered bindings or unknown fields is rejected.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_marked_authority_approval_service_rejects_tamper_and_expiry[bound_task_id-other-ARCHITECTURE_APPROVAL_BINDING_MISMATCH]",
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_marked_authority_approval_service_rejects_tamper_and_expiry[bound_attempt_id-other-ARCHITECTURE_APPROVAL_BINDING_MISMATCH]",
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_marked_authority_approval_service_rejects_tamper_and_expiry[candidate_commit_sha-ffffffffffffffffffffffffffffffffffffffff-ARCHITECTURE_APPROVAL_BINDING_MISMATCH]",
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_marked_authority_approval_service_rejects_tamper_and_expiry[candidate_tree_sha-ffffffffffffffffffffffffffffffffffffffff-ARCHITECTURE_APPROVAL_BINDING_MISMATCH]",
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_marked_authority_approval_service_rejects_tamper_and_expiry[authority_findings_sha256-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb-ARCHITECTURE_APPROVAL_BINDING_MISMATCH]",
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_marked_authority_approval_service_rejects_tamper_and_expiry[unknown-reject-ARCHITECTURE_APPROVAL_UNKNOWN_FIELDS]",
        ),
    ),
    _c(
        "GB-032",
        "One-shot approval replay is idempotent",
        "security",
        "idempotency",
        "A one-shot approval action is atomically consumed and replay cannot duplicate the effect.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_versioned_allow_action_once_is_consumed_atomically_and_replay_is_idempotent",
        ),
    ),
    _c(
        "GB-033",
        "Retry keeps task identity",
        "invariant",
        "recovery",
        "Terminal retry preserves task identity and increments attempt identity.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_terminal_retry_keeps_task_identity_and_increments_attempt",
        ),
    ),
    _c(
        "GB-034",
        "Retry does not duplicate semantic task",
        "invariant",
        "idempotency",
        "Retry reuses the terminal request rather than creating a duplicate semantic task.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_retry_task_reuses_terminal_request_without_duplicate_task",
        ),
    ),
    _c(
        "GB-035",
        "Retry history is append-only",
        "invariant",
        "recovery",
        "A retry creates attempt-scoped identity without mutating prior history.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_retry_task_creates_attempt_scoped_identity_without_mutating_history",
        ),
    ),
    _c(
        "GB-036",
        "Idempotency key binds exact request",
        "security",
        "idempotency",
        "An idempotency key is duplicate-only for the same exact action request.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_idempotency_key_is_duplicate_only_for_same_exact_action_request",
        ),
    ),
    _c(
        "GB-037",
        "Retry action rebinds fresh attempt",
        "security",
        "recovery",
        "Action-bound retry must bind the fresh attempt identity.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_action_bound_retry_rebinds_envelope_to_fresh_attempt_identity",
        ),
    ),
    _c(
        "GB-038",
        "Semantic contract change blocks retry",
        "security",
        "stale_state",
        "Retry rejects non-revision contract changes instead of silently widening scope.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_terminal_retry_rejects_non_revision_contract_change",
        ),
    ),
    _c(
        "GB-039",
        "Pending candidate blocks retry",
        "invariant",
        "partial_state",
        "A pending Candidate must be disposed or superseded before retry.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_pending_candidate_blocks_retry_until_superseded",
        ),
    ),
    _c(
        "GB-040",
        "Integration rechecks exact Candidate",
        "security",
        "stale_state",
        "Approved integration revalidates the exact Candidate immediately before integration.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_integrate_approved_rechecks_exact_candidate_before_integration",
        ),
    ),
    _c(
        "GB-041",
        "Locked integration boundary rechecks identity",
        "security",
        "stale_state",
        "Candidate identity is checked again at the locked apply boundary.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_integrate_approved_rechecks_again_at_locked_apply_boundary",
        ),
    ),
    _c(
        "GB-042",
        "Exact integration is idempotent",
        "invariant",
        "idempotency",
        "Repeating exact approved integration does not integrate twice.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_exact_approved_integration_is_idempotent",
        ),
    ),
    _c(
        "GB-043",
        "Repeated retry keeps one task",
        "regression",
        "recovery",
        "Five terminal retries preserve one durable task identity.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_five_terminal_retries_keep_one_task_identity",
        ),
    ),
    _c(
        "GB-044",
        "Same task with different contract fails",
        "security",
        "authority_conflict",
        "Reusing a task ID for a different contract fails closed.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_same_task_id_different_contract_fails_closed",
        ),
    ),
    _c(
        "GB-045",
        "Wait timeout preserves in-progress",
        "compatibility",
        "partial_state",
        "A bounded wait timeout returns in-progress state rather than failure or cancellation.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_wait_task_timeout_returns_in_progress_envelope",
        ),
    ),
    _c(
        "GB-046",
        "Status reads do not reconcile",
        "invariant",
        "partial_state",
        "Read-only status snapshots do not reconcile or mutate durable state.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_status_snapshot_does_not_reconcile_or_expand_details",
        ),
    ),
    _c(
        "GB-047",
        "Duplicate direct finish has one receipt",
        "invariant",
        "idempotency",
        "Duplicate direct completion reuses the receipt and does not create a second commit.",
        LIFECYCLE,
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_direct_canonical_duplicate_finish_reuses_receipt_without_second_commit",
        ),
    ),
    _c(
        "GB-048",
        "Required action differs from optional retry",
        "regression",
        "partial_state",
        "A cleaned Candidate-less final block may retain an optional retry hint without remaining currently actionable.",
        LIFECYCLE + ("https://github.com/James3014/Nexus-new/issues/22",),
        (
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_clean_candidate_less_final_block_preserves_optional_retry_and_evidence[REMOVED]",
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_clean_candidate_less_final_block_preserves_optional_retry_and_evidence[ALREADY_REMOVED]",
            "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_clean_candidate_less_final_block_preserves_optional_retry_and_evidence[TARGET_CLEANED]",
        ),
    ),
    _c(
        "GB-049",
        "HEAD drift is informational",
        "compatibility",
        "stale_state",
        "Repository HEAD drift alone does not require runtime reload or action review.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_freshness.py::test_head_drift_only_is_informational",
        ),
    ),
    _c(
        "GB-050",
        "Runtime drift requires reload",
        "invariant",
        "stale_state",
        "Loaded runtime-source drift sets reload_required without inventing action review.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_freshness.py::test_runtime_drift_triggers_reload_only",
        ),
    ),
    _c(
        "GB-051",
        "Action contract drift requires review",
        "security",
        "stale_state",
        "Action schema/contract drift requires definition review.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_freshness.py::test_action_contract_drift_requires_review",
        ),
    ),
    _c(
        "GB-052",
        "Unreadable action contract fails closed",
        "security",
        "failure",
        "An unreadable or unparseable action contract requires review rather than stable status.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_freshness.py::test_action_contract_fail_closed_requires_review",
        ),
    ),
    _c(
        "GB-053",
        "Permission fingerprint sees semantic change",
        "security",
        "stale_state",
        "Semantic permission-enforcement changes alter the permission fingerprint.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_freshness.py::test_permission_enforcement_digest_is_sensitive_to_semantic_ast_change",
        ),
    ),
    _c(
        "GB-054",
        "Permission fingerprint ignores formatting",
        "compatibility",
        "boundary",
        "Comments and formatting do not create false permission-policy drift.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_freshness.py::test_permission_enforcement_digest_ignores_comments_and_formatting",
        ),
    ),
    _c(
        "GB-055",
        "Freshness reasons stay separated",
        "regression",
        "partial_state",
        "Combined runtime and review drift keep reload reasons separate from review reasons.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_freshness.py::test_combined_runtime_and_review_drift_keeps_reason_sets_separate",
        ),
    ),
    _c(
        "GB-056",
        "Search falls back when rg is absent",
        "compatibility",
        "failure",
        "Bounded search uses the Python fallback when ripgrep is unavailable.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_search.py::test_search_uses_python_fallback_when_rg_is_missing",
        ),
    ),
    _c(
        "GB-057",
        "Search does not mask rg errors",
        "security",
        "failure",
        "General ripgrep execution errors are surfaced and never masked as fallback success.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_search.py::test_search_does_not_mask_general_rg_execution_error",
        ),
    ),
    _c(
        "GB-058",
        "Search rejects symlink targets",
        "security",
        "malformed_input",
        "Direct or intermediate symlink search targets are rejected before traversal.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_search.py::test_direct_symlink_file_target_is_rejected",
            "tests/contracts/test_unified_mcp_gateway_search.py::test_intermediate_symlink_directory_is_rejected",
        ),
    ),
    _c(
        "GB-059",
        "Search order is deterministic",
        "compatibility",
        "idempotency",
        "Fallback search returns deterministic result ordering.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_search.py::test_fallback_result_order_is_deterministic",
        ),
    ),
    _c(
        "GB-060",
        "Timed-out search is reaped",
        "security",
        "recovery",
        "A search deadline terminates and reaps the child process without leaking it.",
        GATEWAY,
        (
            "tests/contracts/test_unified_mcp_gateway_search.py::test_rg_backend_enforces_deadline_and_reaps_process",
        ),
    ),
    _c(
        "GB-061",
        "Claim read model cannot mutate runtime",
        "security",
        "authority_conflict",
        "A PASS read model summarizes evidence but cannot authorize runtime update or public benchmark.",
        CLAIM,
        (
            "tests/contracts/test_claim_evidence_read_model.py::test_runtime_apply_read_model_summarizes_gate_refs_without_mutating_runtime",
        ),
    ),
    _c(
        "GB-062",
        "Missing evidence returns",
        "invariant",
        "failure",
        "Runtime review without evidence bundle and receipts returns explicit blockers.",
        CLAIM,
        (
            "tests/contracts/test_claim_evidence_read_model.py::test_read_model_blocks_runtime_review_without_bundle_and_receipts",
        ),
    ),
    _c(
        "GB-063",
        "Public claim requires clean provider tokens",
        "security",
        "failure",
        "Public-ready claims fail closed when provider-token cleanliness is missing.",
        CLAIM,
        (
            "tests/contracts/test_claim_evidence_read_model.py::test_public_read_model_requires_clean_provider_tokens",
        ),
    ),
    _c(
        "GB-064",
        "Read-model unlock injection is rejected",
        "security",
        "malformed_input",
        "A read-model payload cannot inject runtime/public unlocks.",
        CLAIM,
        (
            "tests/contracts/test_claim_evidence_read_model.py::test_validate_rejects_attempted_unlocks_from_read_model_payload",
        ),
    ),
    _c(
        "GB-065",
        "Required evidence must be sealed and hash-valid",
        "security",
        "stale_state",
        "When sealing is required, unsealed or hash-invalid evidence fails validation.",
        CLAIM,
        (
            "tests/contracts/test_claim_evidence_read_model.py::test_read_model_requires_sealed_and_hash_valid_evidence_when_requested",
        ),
    ),
    _c(
        "GB-066",
        "Completion PASS requires an envelope",
        "invariant",
        "partial_state",
        "A completion PASS claim requires its exact completion envelope.",
        CLAIM,
        (
            "tests/contracts/test_claim_evidence_read_model.py::test_runtime_read_model_requires_completion_envelope_when_completion_passes",
        ),
    ),
    _c(
        "GB-067",
        "Failed completion envelope blocks claim",
        "regression",
        "failure",
        "A failed completion envelope keeps runtime review blocked.",
        CLAIM,
        (
            "tests/contracts/test_claim_evidence_read_model.py::test_runtime_read_model_blocks_failed_completion_envelope_in_contract",
        ),
    ),
    _c(
        "GB-068",
        "Unadmitted persistent documents are blocked",
        "security",
        "authority_conflict",
        "A new persistent Markdown document outside admitted task scope is blocked.",
        REPO_GATE,
        (
            "tests/nexus/orchestrator/test_repository_contract_gate.py::test_new_persistent_markdown_outside_tasks_blocked",
        ),
    ),
    _c(
        "GB-069",
        "Parallel router modules are blocked",
        "security",
        "authority_conflict",
        "A new production Agent/Router/wrapper module that creates parallel authority is blocked.",
        REPO_GATE,
        (
            "tests/nexus/orchestrator/test_repository_contract_gate.py::test_new_production_python_module_denoting_agent_router_wrapper_is_blocked",
        ),
    ),
    _c(
        "GB-070",
        "Authority change needs exact one-shot approval",
        "security",
        "authority_conflict",
        "Committed authority changes require exact approval and approval replay is blocked.",
        REPO_GATE,
        (
            "tests/nexus/orchestrator/test_repository_contract_gate.py::test_committed_authority_change_requires_exact_approval_and_replay_is_blocked",
        ),
    ),
    _c(
        "GB-071",
        "Candidate head drift blocks recheck",
        "security",
        "stale_state",
        "Repository contract recheck rejects Candidate head drift.",
        REPO_GATE,
        (
            "tests/nexus/orchestrator/test_repository_contract_gate.py::test_identity_recheck_blocks_candidate_head_drift",
        ),
    ),
    _c(
        "GB-072",
        "Execution topology config cannot bypass freeze",
        "security",
        "authority_conflict",
        "A new execution-topology configuration is blocked by the architecture freeze.",
        REPO_GATE,
        (
            "tests/nexus/orchestrator/test_repository_contract_gate.py::test_new_execution_topology_config_is_blocked",
        ),
    ),
    _c(
        "GB-073",
        "Learning episode identity is stable",
        "invariant",
        "idempotency",
        "Equivalent learning evidence produces stable episode and idempotency identities.",
        LEARNING,
        (
            "tests/learning/test_nexus_learning_episode_contract.py::test_episode_identity_and_stages_are_stable_and_fail_closed",
        ),
    ),
    _c(
        "GB-074",
        "Applied lessons are bounded by retrieval",
        "security",
        "malformed_input",
        "A forged lesson not present in retrieval cannot be recorded as applied.",
        LEARNING,
        (
            "tests/learning/test_nexus_learning_episode_contract.py::test_applied_lessons_are_bounded_by_retrieval",
        ),
    ),
    _c(
        "GB-075",
        "Uplift requires paired verifier evidence",
        "invariant",
        "failure",
        "Outcome uplift requires paired memory-off/on verifier results with the same task fingerprint.",
        LEARNING,
        (
            "tests/learning/test_nexus_learning_episode_contract.py::test_uplift_requires_paired_memory_verifiers_with_same_fingerprint",
        ),
    ),
    _c(
        "GB-076",
        "Verified Repair evidence frontier",
        "regression",
        "partial_state",
        "VERIFIED_REPAIR must require physical failing baseline, frozen oracle identity, same-oracle PASS, regression PASS, and required mutation adequacy.",
        (
            "https://github.com/James3014/Nexus-new/issues/16",
            "https://github.com/James3014/Nexus-new/pull/41",
        ),
        status="finding",
        finding_id="GBF-001",
    ),
    _c(
        "GB-077",
        "Current live Gateway identity",
        "invariant",
        "stale_state",
        "Live Gateway verification must bind current loaded source, action manifest, permission policy, worker identity, and negative controls.",
        ("https://github.com/James3014/Nexus-new/issues/12",),
        status="finding",
        finding_id="GBF-002",
    ),
    _c(
        "GB-078",
        "Same-task Online consumes exact Local evidence",
        "invariant",
        "partial_state",
        "Online execution must consume the exact identity-bound Local result; adjacent executions are insufficient.",
        ("https://github.com/James3014/Nexus-new/issues/29",),
        status="finding",
        finding_id="GBF-003",
    ),
    _c(
        "GB-079",
        "Canonical task continuity",
        "compatibility",
        "recovery",
        "Resume must deterministically rebuild task state from immutable events and fail closed on stale or tampered identity.",
        ("https://github.com/James3014/Nexus-new/issues/31",),
        status="finding",
        finding_id="GBF-004",
    ),
    _c(
        "GB-080",
        "World A final claims bind evidence",
        "security",
        "authority_conflict",
        "Final natural-language verification and absence claims must be bound to evidence or downgraded to not verified.",
        ("https://github.com/James3014/Nexus-new/issues/40",),
        status="finding",
        finding_id="GBF-005",
    ),
    _c(
        "GB-081",
        "Policy Lane fixtures track authoritative manifest",
        "regression",
        "stale_state",
        "Policy Lane hard-lane fixtures and count assertions must track the existing authoritative manifest.",
        (
            "https://github.com/James3014/Nexus-new/issues/42",
            "https://github.com/James3014/Nexus-new/pull/43",
            "docs/reports/policy-manifest.v2.json",
            "scripts/ops/check_policy_lane_gate.py",
        ),
        (
            "tests/ops/test_policy_lane_gate.py::TestHardLane::test_hard_lane_modify_without_drill_blocked",
            "tests/ops/test_policy_lane_gate.py::TestManifestStructure::test_manifest_loads",
            "tests/ops/test_policy_lane_gate.py::TestManifestStructure::test_hard_lane_count_increased",
        ),
    ),
    _c(
        "GB-082",
        "Workforce preference wording is not route authority",
        "security",
        "authority_conflict",
        "Worker/model preference guidance must remain downstream of CapabilityPlanner and fresh Workforce Admission; model ordering cannot choose routes, capabilities, topology, governance depth, or claim authority.",
        (
            "https://github.com/James3014/Nexus-new/issues/44",
            "AGENTS.md#Authority invariants",
            "docs/arch/MODEL_WORKFORCE_POLICY.md",
        ),
        finding_probe="workforce_wording",
        status="finding",
        finding_id="GBF-007",
    ),
    _c(
        "GB-083",
        "Policy manifest updater is idempotent",
        "regression",
        "idempotency",
        "Running the drill-manifest updater twice must be byte-identical after the first run, preserve unique policy IDs, and recompute every lane projection from the final policy list.",
        (
            "https://github.com/James3014/Nexus-new/issues/45",
            "scripts/ops/update_manifest_drills.py",
            "docs/reports/policy-manifest.v2.json",
        ),
        finding_probe="manifest_updater_idempotency",
        status="finding",
        finding_id="GBF-008",
    ),
)


FINDINGS = {
    "GBF-001": "Issue #16 is READY and PR #41 is open; the behavior is not merged into main 7d49e161dcd2e6ceebba9934f3318716853c3728.",
    "GBF-002": "Issue #12 remains open verification-first; current live Gateway/source identity is not proven by the source snapshot alone.",
    "GBF-003": "Issue #29 states same-task Online consumption of exact Local evidence remains unproven.",
    "GBF-004": "Issue #31 is blocked on #7 and records missing canonical retained-state compaction/resume behavior.",
    "GBF-005": "Issue #40 is validation-first and has not yet proven a World A final-response enforcement seam.",
    "GBF-007": "Issue #44 records residual model-order routing wording in Workforce policy; current runtime is not thereby proven to have a second router.",
    "GBF-008": "Issue #45 records non-idempotent drill-manifest updates and stale lane-distribution projections; policy semantics must not be changed to close it.",
}
