from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_FILES = (
    "AGENTS.md",
    "MUSE_PROTO.md",
    "GEMINI.md",
    ".gemini/GEMINI.md",
    "CLAUDE.md",
    "MEMORY.md",
    "SOUL.md",
    ".cursorrules",
)
FORBIDDEN_TOKENS = (
    "nexus-sync",
    "STATE.yaml",
    "Nexus-Singularity-V17",
    "Nexus-Singularity-V26",
    "AGENT_MANDATORY_PROTOCOL.md",
    "/Users/jameschen/Workspace/nexus/",
    '--filter "domain=tech"',
)
AUTHORITY_FILES = (
    "AGENTS.md",
    "docs/agents/TASK_EXECUTION_CONTRACT.md",
    "docs/agents/WORKFORCE_EXECUTION_OVERLAY.md",
)


def _norm(text: str) -> str:
    return " ".join(text.split())


def _authority_texts() -> dict[str, str]:
    return {path: (ROOT / path).read_text(encoding="utf-8") for path in AUTHORITY_FILES}


def test_bootstrap_files_use_current_worktree_authority():
    contents = {path: (ROOT / path).read_text(encoding="utf-8") for path in BOOTSTRAP_FILES}
    for path, content in contents.items():
        assert not any(token in content for token in FORBIDDEN_TOKENS), path

    assert "active Git-tracked Task Card" in contents["AGENTS.md"]
    assert "DIRECT_CANONICAL" in contents["AGENTS.md"]
    assert "does not require a Task Card" in contents["AGENTS.md"]
    for path in ("GEMINI.md", "CLAUDE.md", "MEMORY.md", "SOUL.md", ".cursorrules"):
        assert "DIRECT_CANONICAL" in contents[path], path
    assert "MUSE_PROTO.md` is only" in contents["MUSE_PROTO.md"]
    assert "../GEMINI.md" in contents[".gemini/GEMINI.md"]


def test_current_operating_mode_bootstrap_is_direct_first_and_fail_closed():
    import yaml

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")
    mode_path = ROOT / "docs/governance/current_operating_mode.yaml"
    mode = yaml.safe_load(mode_path.read_text(encoding="utf-8"))

    assert mode["schema"] == "nexus.operating_mode.v1"
    assert mode["mode"] == "BOOTSTRAP"
    assert mode["effective_scope"] == ["nexus-core", "open-swe", "learning-wiring"]
    assert mode["default_execution"]["primary_bounded_work"] == "DIRECT_CANONICAL"
    assert mode["default_execution"]["delegated_bounded_work"] == "DIRECT_DELEGATED"
    assert mode["task_card_required_by_default"] is False
    assert mode["auto_chain"] is False
    assert (
        mode["transition"]["existing_active_work"]
        == "PRESERVE_CURRENT_EXECUTION_CONTRACT_UNTIL_COMPLETION"
    )
    assert mode["transition"]["new_work"] == "READ_CURRENT_OPERATING_MODE"
    assert mode["transition"]["successor_work"] == "READ_CURRENT_OPERATING_MODE"
    assert mode["transition"]["g10_completion"] == "DOES_NOT_CHANGE_DEFAULT_EXECUTION"
    assert mode["transition"]["governance_default_ready"] == "REQUIRES_EXPLICIT_OWNER_DECISION"
    assert mode["transition"]["governed_attempt_authority_failure"] == "BLOCK_REBIND_OR_RECONCILE"
    assert mode["transition"]["silent_governed_to_direct_downgrade"] == "FORBIDDEN"
    readiness = mode["readiness_for_nexus_governance_default"]
    assert readiness["decision_authority"] == "OWNER_ONLY"
    assert readiness["post_decision_effect"] == "SEPARATE_POLICY_CHANGE_REQUIRED"
    assert set(readiness["required_evidence"]) == {
        "representative_real_tasks_end_to_end_under_governed_authority",
        "continuation_timeout_reconcile_and_restart_exercised",
        "nexus_self_modification_without_routine_authority_recursion",
        "task_card_grant_admission_and_execution_contracts_stable_for_normal_work",
        "common_engineering_no_longer_requires_routine_direct_bypass",
        "direct_recovery_path_restores_failed_governance_plane",
    }
    assert (
        mode["fail_closed"]["missing_invalid_or_ambiguous_mode"]
        == "REQUIRE_EXPLICIT_CURRENT_OWNER_LANE"
    )

    escalation = set(mode["escalate_to_governed_when"])
    for required in (
        "nexus_lifecycle_authority_change",
        "route_or_capability_authority_change",
        "workforce_admission_or_worker_authority_change",
        "security_boundary_weakening",
        "authentication_or_authorization_security_semantics",
        "migration_or_schema_authority_change",
        "production_data_mutation_authority",
        "protected_ref_operation_outside_exact_owner_confirmed_pr_merge",
        "release_authority",
        "production_activation",
        "external_irreversible_effect",
        "public_production_claim",
        "break_glass_governance_recovery",
        "owner_selected_governed",
    ):
        assert required in escalation

    assert "read `docs/governance/current_operating_mode.yaml`" in agents.lower()
    assert "Existing active work keeps its\ncurrent execution contract until completion" in agents
    assert "does not switch lanes mid-task" in agents
    assert "fail closed to an\nexplicit current Owner lane decision" in agents
    assert "cannot select\nor override a `CapabilityPlanner` route/capability" in agents
    assert "Current self-hosting stabilization semantics" in agents
    assert "does not by itself change the repository default\nexecution lane" in agents
    assert "must never silently downgrade that attempt" in agents
    assert "`NEXUS_GOVERNANCE_DEFAULT_READY` is an Owner-only transition decision" in agents
    assert "Self-hosting stabilization and future default transition" in contract
    assert "not an automatic repository-wide switch to governed-by-default work" in contract
    assert "must never fall back\nto a direct / `OWNER_DIRECT` attempt" in contract
    assert "may be declared only by the Owner" in contract


def test_direct_canonical_protected_merge_does_not_require_governed_acceptance():
    import yaml

    mode = yaml.safe_load(
        (ROOT / "docs/governance/current_operating_mode.yaml").read_text(encoding="utf-8")
    )
    direct = mode["protected_merge"]["DIRECT_CANONICAL"]

    assert direct["eligible_outcome"] == "DIRECT_MERGE_ELIGIBLE"
    assert direct["merge_sink"] == "git_merge_pull_request"
    assert direct["owner_confirmation_required"] is True
    assert direct["third_party_independent_review_required"] is False
    assert direct["independent_acceptance_hash_required"] is False
    assert direct["standing_grant_required"] is False


def test_direct_delegated_uses_coordinator_verification_not_a_third_reviewer():
    import yaml

    mode = yaml.safe_load(
        (ROOT / "docs/governance/current_operating_mode.yaml").read_text(encoding="utf-8")
    )
    delegated = mode["protected_merge"]["DIRECT_DELEGATED"]

    assert delegated["merge_sink"] == "git_merge_pull_request"
    assert delegated["worker_may_merge"] is False
    assert delegated["coordinator_independent_verification_required"] is True
    assert delegated["third_party_independent_review_required"] is False
    assert delegated["standing_grant_required"] is False


def test_governed_protected_merge_keeps_acceptance_and_authority_fail_closed():
    import yaml

    mode = yaml.safe_load(
        (ROOT / "docs/governance/current_operating_mode.yaml").read_text(encoding="utf-8")
    )
    governed = mode["protected_merge"]["GOVERNED"]

    assert governed["merge_sink"] == "github_complete_pull_request"
    assert governed["independent_acceptance_required"] is True
    assert governed["machine_verifiable_acceptance_provenance_required"] is True
    assert governed["standing_grant_required"] is True
    assert governed["github_merge_action_required"] is True


def test_high_risk_authority_effects_still_escalate_to_governed():
    import yaml

    mode = yaml.safe_load(
        (ROOT / "docs/governance/current_operating_mode.yaml").read_text(encoding="utf-8")
    )
    escalation = set(mode["escalate_to_governed_when"])

    assert {
        "route_or_capability_authority_change",
        "workforce_admission_or_worker_authority_change",
        "nexus_lifecycle_authority_change",
        "security_boundary_weakening",
        "authentication_or_authorization_security_semantics",
        "production_data_mutation_authority",
        "migration_or_schema_authority_change",
        "release_authority",
        "production_activation",
        "external_irreversible_effect",
        "public_production_claim",
        "break_glass_governance_recovery",
        "owner_selected_governed",
    }.issubset(escalation)


def test_repository_identity_never_selects_governed_merge_lane():
    import yaml

    mode = yaml.safe_load(
        (ROOT / "docs/governance/current_operating_mode.yaml").read_text(encoding="utf-8")
    )

    assert mode["lane_selection_basis"] == "AUTHORITY_EFFECT_AND_RISK_NOT_REPOSITORY_IDENTITY"
    assert "James3014/Nexus-new" not in mode["escalate_to_governed_when"]
    assert "REPOSITORY_IDENTITY_DOES_NOT_SELECT_EXECUTION_OR_MERGE_LANE" in mode["principles"]


def test_execution_domains_and_candidate_namespaces_are_unambiguous():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")
    launch = (ROOT / ".agents/skills/nexus-task-launch/SKILL.md").read_text(encoding="utf-8")
    merge = (ROOT / ".agents/skills/nexus-merge-gate/SKILL.md").read_text(encoding="utf-8")

    assert "current_operating_mode.yaml" in agents
    assert "the Owner explicitly selects a different lane" in agents
    assert "does not select local lifecycle" in agents
    assert "A GitHub PR Candidate" in agents
    assert "a local lifecycle Candidate" in agents
    assert "never substitutes for program correctness" in _norm(agents)
    assert "Reviewer block/card omission is not\n  terminal `REJECTED`" in agents

    assert "GitHub collaboration and local lifecycle domains" in contract
    assert "does not enter local lifecycle merely because it is\ndelegated" in contract
    assert "not the admission or merge gate for ordinary GitHub PR work" in contract
    assert "must not create, widen, or recursively bootstrap" in contract
    assert "not automatically a\nterminal `REJECTED` Candidate" in contract

    assert "This skill governs only the\nlocal Nexus self-hosted lifecycle" in launch
    assert "Ordinary GitHub\nReady-Issue branch work does not enter this skill" in launch
    assert "That handoff applies only to a local lifecycle Candidate" in launch

    assert "applies exclusively to a local Nexus lifecycle Candidate" in merge
    assert "It is not the merge procedure for a GitHub PR Candidate" in merge


def test_ready_issue_claim_contract_is_worker_neutral_and_fail_closed():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")

    assert "eligible governed worker" in agents
    assert "Provider/model names are not normative" in agents
    for token in (
        "claim_intent",
        "claim_enforcement_state",
        "claim_mode",
        "PROJECTION_ONLY",
        "UNKNOWN",
        "MANUAL_DISPATCH",
        "assignees, labels, comments, Project fields, branch names",
    ):
        assert token in agents
        if token != "assignees, labels, comments, Project fields, branch names":
            assert token in contract
    assert "GitHub UI metadata and branch names remain" in contract
    assert "canonical atomic/fenced claim operation" in contract
    assert "never grants\n  route selection" in contract


def test_protected_merge_requires_exact_owner_slot_not_standing_grant():
    """Legacy node ID retained; assertions enforce DIRECT/GOVERNED lane separation."""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")
    merge = (ROOT / ".agents/skills/nexus-merge-gate/SKILL.md").read_text(encoding="utf-8")
    current = (
        ROOT / "tasks/standing-owner-autonomy-20260811/02-standing-grant-normal-phase-authority.md"
    ).read_text(encoding="utf-8")
    historical_card = (
        ROOT / "tasks/standing-owner-autonomy-20260811/01-standing-coordinator-authority.md"
    ).read_text(encoding="utf-8")

    normalized_agents = _norm(agents)
    assert "Merge follows lane, not repository" in normalized_agents
    assert "DIRECT uses `git_merge_pull_request`" in normalized_agents
    assert "no Task Card, third-party approval, acceptance receipt/hash" in normalized_agents
    assert "GOVERNED retains independent acceptance" in normalized_agents
    assert "It grants no delegated-worker merge authority" in agents
    assert "For `DIRECT_CANONICAL`, the primary coordinator may use" in contract
    assert "Neither direct lane requires a third-party GitHub `APPROVED` review" in contract
    workflow = (ROOT / ".github/workflows/trusted-deletion-anchor.yml").read_text(encoding="utf-8")
    assert "nexus.merge_lane_binding.v1" in agents
    assert "nexus.merge_lane_binding.v1" in contract
    assert "nexus.owner_execution_lane_rebind.v1" in agents
    assert "nexus.owner_execution_lane_rebind.v1" in contract
    assert "scripts/ops/trusted_merge_lane_gate.py" in agents
    assert "scripts/ops/trusted_merge_lane_gate.py" in contract
    assert "Starting with PR #1061" in agents
    assert "Starting with PR #1061" in contract
    assert "Trusted verifier (default branch)" in agents
    assert "Trusted verifier (default branch)" in contract
    assert "types: [opened, synchronize, reopened, ready_for_review, edited]" in workflow
    assert "trusted_merge_lane_gate.py" in workflow
    assert "merge-lane-gate.json" in workflow
    assert "For `GOVERNED`, the primary coordinator may prepare `MERGE_INTENT`" in contract
    assert "Any PR/head/base/main or evidence drift invalidates" in _norm(contract)
    assert "protected-merge semantics follow the already-selected execution lane" in _norm(merge)
    assert "The direct merge sink is the server-bound `git_merge_pull_request`" in _norm(merge)
    assert "For `GOVERNED`, keep the existing independent acceptance" in merge
    assert "ordinary phases from Task Card through main" in current
    assert "PLATFORM_APPROVAL_REQUIRED" in current
    assert "status: HISTORICAL_SUPERSEDED_BY_ISSUE_163_NORMAL_PHASE_AUTHORITY" in historical_card
    assert "per-phase merge-slot restriction is historical and superseded" in historical_card


def test_current_standing_grant_contract_is_non_self_attesting():
    index = (ROOT / "tasks/standing-owner-autonomy-20260811/INDEX.md").read_text(encoding="utf-8")
    current = (
        ROOT / "tasks/standing-owner-autonomy-20260811/02-standing-grant-normal-phase-authority.md"
    ).read_text(encoding="utf-8")

    assert "frontier: 02-standing-grant-normal-phase-authority.md" in index
    assert "normative CURRENT AUTHORITY CONTRACT" in current
    assert "does not itself attest" in current
    assert "does not itself authorize a merge" in current
    for field in (
        "grant_id",
        "owner",
        "primary coordinator",
        "repository",
        "source_thread",
        "Goal",
        "issued_at",
        "expiry",
        "revocation_state",
        "context_hash",
    ):
        assert f"`{field}`" in current
    assert "`GITHUB_MERGE`" in current
    assert "separate physical, machine-bound Owner receipt" in current


def test_standing_grant_receipt_path_is_machine_local_and_loader_is_required():
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    store = (ROOT / "nexus/orchestrator/standing_grant_store.py").read_text(encoding="utf-8")

    assert ".local/state/nexus/authority/standing-grants/" in contract
    assert "independent lock/CAS" in contract
    assert "read-only compatibility" in contract
    assert "durable" in agents
    assert "load_standing_grant_receipt" in store
    assert "write_standing_grant_receipt" in store
    assert "StandingGrantKey" in store
    assert "Atomic durable write" in store


def test_bootstrap_file_set_is_complete_and_tracked():
    for path in BOOTSTRAP_FILES:
        assert (ROOT / path).is_file(), path


def test_open_swe_task_cards_have_exact_bindings_and_disable_auto_chain():
    campaign_root = ROOT / "tasks/open-swe-execution-productionization-v1"
    for task_id in ("TASK-001", "TASK-002", "TASK-003", "TASK-004"):
        card = (campaign_root / f"{task_id}.md").read_text(encoding="utf-8")
        assert card.count(f"task_id: `{task_id}`") == 1
        assert "- **Auto-chain:** `false`" in card


def test_external_bootstrap_recovery_boundary_is_fail_closed():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs/governance/rollback_runbook.md").read_text(encoding="utf-8")
    normalized_runbook = " ".join(runbook.split())

    assert "self-hosting/controller identity contract is itself under repair" in agents
    assert "bounded external bootstrap procedure" in agents
    assert "never implies approval, integration, push, reload, or activation" in agents

    for required in (
        "identity, action-authorization, or state-transition contract",
        "ordinary provider, model, quota, test",
        "correctly blocking healthy lifecycle failure",
        "normal governed path",
        "exact known-clean repository base",
        "external clean repair worktree",
        "Never copy a",
        "whole file or commit from a dirty canonical checkout",
        "exact parent, tree, and full diff",
        "source/runtime/action identity is missing, substituted, stale, or tampered",
        "positive, negative, tamper, retry/idempotency",
        "same `task_id`",
        "fresh `attempt_id`",
        "`action_id`, and `idempotency_key`",
        "must not create a second Controller",
        "independent review",
        "distinct from the implementer",
        "permanent alternative lifecycle",
        "`CapabilityPlanner` remains the sole route",
        "`HybridRouteDecision` remains only its derived decision projection",
    ):
        assert required in normalized_runbook

    assert "repair completion performs none of them" in normalized_runbook
    assert "Resume the normal governed path" in normalized_runbook


def test_direct_delegated_contract_is_explicit_and_bounded():
    texts = _authority_texts()
    agents = _norm(texts["AGENTS.md"])
    combined = _norm(" ".join(texts.values()))

    assert "DIRECT_DELEGATED" in agents
    assert "exactly one bounded external worker" in agents
    assert "No Nexus Task Card, Nexus lifecycle, CapabilityPlanner routing" in agents
    assert "delegation alone does not escalate" in agents
    assert "independently inspects the physical diff" in agents
    assert "AUTO_CHAIN=false" in agents
    assert "DIRECT_DELEGATED_BLOCKED" in combined
    assert (
        "direct external delegation boundary"
        in _norm(texts["docs/agents/WORKFORCE_EXECUTION_OVERLAY.md"]).lower()
    )
    assert (
        "Direct work becomes governed before mutation if it delegates implementation"
        not in texts["AGENTS.md"]
    )


def test_task_execution_contract_preserves_direct_delegated_exception():
    contract = _authority_texts()["docs/agents/TASK_EXECUTION_CONTRACT.md"]
    normalized = _norm(contract)

    assert "DIRECT_DELEGATED" in contract
    assert "not required solely because implementation is delegated" in normalized
    assert "exceeds the `DIRECT_DELEGATED` boundary" in normalized
    assert "Nexus lifecycle/Candidate authority" in normalized
    assert "changes route/lifecycle/workforce/security authority" in normalized
    assert (
        "An exact Owner-confirmed protected PR merge is not by itself such a condition"
        in normalized
    )
    assert "production/public claim" in normalized
    assert (
        "Escalate to this governed contract before mutation when implementation is delegated"
        not in contract
    )


def test_direct_external_delegation_does_not_inherit_nexus_workforce_admission():
    overlay = _authority_texts()["docs/agents/WORKFORCE_EXECUTION_OVERLAY.md"]
    normalized = _norm(overlay)

    assert "DIRECT_DELEGATED" in overlay
    assert "does NOT use Nexus Workforce Admission" in normalized
    assert (
        "Nexus runtime model execution always requires fresh Nexus Workforce Admission"
        in normalized
    )
    assert "transport/execution evidence only" in normalized
    assert "grants no Nexus" in normalized
    assert "route, admission, approval, integration, merge, release" in normalized
    assert "non-self-approving" in normalized
    assert "Local output and delegated output are candidates" in normalized


def test_semantic_authority_delta_contract_is_fail_closed_future_only_and_lane_preserving():
    texts = _authority_texts()
    agents = _norm(texts["AGENTS.md"])
    contract = _norm(texts["docs/agents/TASK_EXECUTION_CONTRACT.md"])

    for text in (agents, contract):
        assert "AUTHORITY_PRESERVING_EVIDENCE_WRITEBACK" in text
        assert "semantic authority" in text.lower()
        assert "DIRECT_CANONICAL" in text
        assert "DIRECT_DELEGATED" in text
        assert "GOVERNED" in text
        assert "filename" in text.lower()
        assert "line-count" in text.lower()
        assert "autonomy" in text.lower()
        assert "worker/provider/model" in text or "provider/model/worker" in text
        assert "default route" in text.lower() or "route/default" in text.lower()
        assert "CapabilityPlanner" in text
        assert "parser" in text.lower()
        assert "verifier" in text.lower()
        assert "claim" in text.lower()
        assert "security" in text.lower()
        assert "migration/schema" in text.lower()
        assert "production-data" in text.lower()
        assert "future" in text.lower()
        assert "retroactive" in text.lower()

    assert "not a fourth execution lane" in agents.lower()
    assert "Any changed, missing, malformed, contradictory, unknown" in agents
    assert "GOVERNED_REQUIRED" in texts["docs/agents/TASK_EXECUTION_CONTRACT.md"]
    assert "does not approve" in contract.lower()
    assert "future-only after this contract is integrated into `main`" in contract
    assert "future-only after independent acceptance" not in contract
    assert "after this contract is integrated into `main`" in agents
    assert "MERGE_INTENT" in texts["AGENTS.md"]


def test_first_issue_bound_action_requires_project_entry_before_governed_effects():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    normalized = _norm(agents)

    assert "Project-entry invariant (#842)" in agents
    assert "MUST call `nexus_project_entry` before any Nexus-governed effectful action" in normalized
    assert "`continue ... #N`, `處理 #N`, `幫我修 #N`" in agents
    assert "If Project Entry is not `READY_TO_EXECUTE`" in normalized
    assert "STOP the governed effect path" in normalized
    assert "Do not jump directly to `nexus_task_card_create`" in normalized
    assert "Switching repository or Issue invalidates the prior Project Entry binding" in normalized
    assert "Direct lanes remain governed by their existing lane rules" in normalized
