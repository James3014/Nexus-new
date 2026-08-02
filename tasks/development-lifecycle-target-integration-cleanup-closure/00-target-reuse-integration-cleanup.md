# Target Reuse, Integration and Cleanup Closure

```yaml
task_id: target-reuse-integration-cleanup-closure
campaign_id: development-lifecycle-target-integration-cleanup-closure
attempt_id: codex-target-integration-cleanup-20260802-a3
status: ACTIVE_CORRECTIVE_ATTEMPT
prior_candidate: 657a2e9f13df7073c33b8c00c75c6f26a95c4bfe
prior_verdict: REJECT_CANDIDATE
owner_activation: granted_for_implementation_candidate
auto_chain: false
source_base:
  canonical_root: /Users/jameschen/Workspace/nexus
  canonical_branch: nexus/integration/main
  committed_head: e16a99977b3e04cc1b34e88ea7dd32c6d80c06cc
  dirty_baseline:
    - nexus/research/epistemic_benchmark/cli.py
    - nexus/research/epistemic_benchmark/contracts.py
    - nexus/research/epistemic_benchmark/packets.py
    - tests/research/test_epistemic_benchmark_cli.py
    - tests/research/test_epistemic_benchmark_e2e.py
    - tests/research/test_epistemic_benchmark_packets.py
target:
  target_id: target-reuse-integration-cleanup-closure
  target_path: /private/tmp/nexus-target-integration-cleanup-closure
  target_branch: nexus/task/target-integration-cleanup-closure
  base: e16a99977b3e04cc1b34e88ea7dd32c6d80c06cc
```

## Owner amendment

```yaml
owner_amendment:
  date: 2026-08-02
  prior_blocker: WORKFORCE_DEPENDENCY_NOT_INDEPENDENTLY_ACCEPTED
  disposition: DOWNGRADED_TO_NON_BLOCKING_DEFERRED_DEPENDENCY
  reason:
    - workforce assignment and target integration are orthogonal authority domains
    - this task does not modify or integrate workforce candidate files
    - transactional behavior can be proven with task-owned Git canaries
  status: ACTIVE_OWNER_RESUMED
```

## G0 authority freeze and exact scope

```yaml
authority_freeze:
  existing_target_authority: nexus/orchestrator/worktree_manager.py and SelfHostedTaskService workspace-slot/lifecycle methods
  existing_candidate_authority: nexus/orchestrator/candidate_commit.py and SelfHostedTaskService candidate capture/promotion methods
  existing_acceptance_authority: nexus/orchestrator/candidate_verifier.py plus persisted promotion binding; implementer output is not acceptance
  existing_integration_authority: nexus/orchestrator/governed_integration.py and SelfHostedTaskService.integrate_approved
  existing_cleanup_authority: nexus/orchestrator/worktree_manager.py.cleanup_terminal_target and SelfHostedTaskService.cleanup_tasks
  existing_registry: Git worktree registry plus lifecycle lease/state owned by the existing services
  public_seams: nexus/orchestrator/unified_mcp_gateway.py candidate approval/integration actions and workspace-slot lifecycle methods
  missing_seams: one typed target/integration/cleanup decision contract and one thin adapter composing the existing authorities
  selected_extension_seam: nexus/orchestrator/target_integration_lifecycle.py delegates Git operations and lifecycle state decisions without creating a second registry, verifier, router, or receipt store
```

```yaml
allowed_files:
  production:
    - nexus/contracts/target_integration_lifecycle.py
    - nexus/orchestrator/target_integration_lifecycle.py
  tests:
    - tests/contracts/test_target_integration_lifecycle.py
    - tests/nexus/orchestrator/test_target_integration_lifecycle.py
    - tests/nexus/orchestrator/test_target_integration_git_canary.py
  governance:
    - tasks/development-lifecycle-target-integration-cleanup-closure/INDEX.md
    - tasks/development-lifecycle-target-integration-cleanup-closure/00-target-reuse-integration-cleanup.md
ceilings:
  production: 8
  tests: 5
  governance: 2
  deletions: 0
forbidden:
  - CapabilityPlanner
  - HybridRouteDecision
  - Workforce selection or admission
  - model/provider/runtime phase behavior
  - protected-main policy
  - production deployment
  - remote push
  - canonical dirty Research files
  - existing Workforce Target or candidate
```

## Gates and acceptance

G0 discovery/authority freeze, G1 target resolution/reuse, G2 candidate and
external acceptance boundary, G3 one-confirmation authorization envelope, G4
transactional staging, G5 cleanup eligibility/execution, G6 real Git canary
and affected regression, G7 Candidate settlement.

The adapter must fail closed on task/card/candidate/plan/canonical drift,
dirty or unowned Targets, missing external acceptance, unverified staging,
and incomplete durable protection. Synthetic receipts are test fixtures only;
Git ancestry, merge conflicts, worktree registration, dirty/untracked state,
and staging are real.

Required focused tests include same-task Target reuse, rejected retry with a
new attempt, external acceptance separation, authorization drift, staging
failure/conflict/canonical drift, cleanup retention/eligibility, persisted
receipt round-trip, and terminal reload.

Exact focused evidence names:

```text
test_same_task_retry_reuses_target
test_rejected_candidate_reuses_same_target_with_new_attempt
test_new_stable_task_creates_new_target
test_unowned_target_is_not_reused
test_implementer_pass_does_not_mark_candidate_accepted
test_authorization_and_cleanup_fail_closed_on_drift
test_receipt_binding_is_caller_persisted_and_round_trips
test_real_git_staging_failure_and_success_do_not_fake_ancestry
test_real_git_canary_detects_canonical_drift_and_applies_verified_result
test_real_git_conflict_and_owned_cleanup_are_fail_closed
```

## Verification

```text
M0: canonical/Target preflight and worktree inventory
M1: focused contract and lifecycle tests
M2: lifecycle adapter tests
M3: real Git canary tests
M4: all existing affected test modules selected non-zero
M5: git diff --check, deletion audit, scoped diff/stat audit
```

## Claim boundary

```text
IMPLEMENTER_VERIFIED_TARGET_REUSE_INTEGRATION_CLEANUP_CANDIDATE
```

This Candidate does not claim independent acceptance, canonical integration,
live Target cleanup, push, or production/public readiness.

## Corrective closure requirements

```yaml
prior_rejection_defects:
  - integration_without_external_acceptance_or_owner_authorization
  - forged_cleanup_decision_could_remove_worktree
  - adapter_owned_a_second_git_integration_and_cleanup_executor
  - dirty_canonical_hash_could_be_accepted_as_clean
  - multiple_active_targets_raised_untyped_value_error
  - receipt_test_did_not_reload_a_fresh_service
  - post_apply_verification_was_missing
corrective_attempt:
  attempt_id: codex-target-integration-cleanup-20260802-a3
  starting_target_head: 657a2e9f13df7073c33b8c00c75c6f26a95c4bfe
  canonical_observed_head: ba6b7c1f7bd0817e759ce68ff73687afb5ff81f8
  canonical_drift: true
  reuse_target_without_rebase_or_reset: true
  claim_ceiling: IMPLEMENTER_VERIFIED_TARGET_REUSE_INTEGRATION_CLEANUP_CANDIDATE
```

## Corrective scope freeze

```yaml
production:
  - nexus/contracts/target_integration_lifecycle.py
  - nexus/orchestrator/target_integration_lifecycle.py
  - nexus/orchestrator/governed_integration.py
  - nexus/orchestrator/self_hosted_task_service.py
  - nexus/orchestrator/worktree_manager.py
tests:
  - tests/contracts/test_target_integration_lifecycle.py
  - tests/nexus/orchestrator/test_target_integration_lifecycle.py
  - tests/nexus/orchestrator/test_target_integration_git_canary.py
  - tests/nexus/orchestrator/test_target_integration_authority_closure.py
  - tests/nexus/orchestrator/test_governed_integration.py
  - tests/nexus/orchestrator/test_self_hosted_task_service.py
  - tests/nexus/orchestrator/test_worktree_manager.py
governance:
  - tasks/development-lifecycle-target-integration-cleanup-closure/INDEX.md
  - tasks/development-lifecycle-target-integration-cleanup-closure/00-target-reuse-integration-cleanup.md
conditional_scope:
  path: nexus/orchestrator/self_hosted_task_service.py
  failing_test: corrective authority and fresh-reload receipt tests
  direct_dependency: existing owner_finish/approve_promotion/integrate_approved/cleanup_tasks state path
  reason: expose the existing authoritative persistence and owner execution sequence
  authority_impact: none
```

## Settlement evidence

```yaml
implementation_commit: ab7dca3f8a0d805bc442f1d2d211dc9a6a6e8f14
canonical_unchanged: true
target_branch: nexus/task/target-integration-cleanup-closure
focused_tests: 8_passed
affected_regressions:
  lifecycle_action: 9_passed
  candidate_commit: 13_passed
  candidate_verifier: 19_passed
  governed_integration: 5_passed
  worktree_cleanup_and_lease: 11_passed
  self_hosted_cleanup_promotion_integration_retry: 28_passed
real_git_canary:
  staging_failure_canonical_unchanged: true
  conflict_canonical_unchanged: true
  dirty_canonical_blocked: true
  verified_apply_passed: true
  owned_cleanup_passed: true
authority_audit:
  new_lifecycle_authority: false
  new_integration_authority: false
  new_verifier: false
  new_receipt_store: false
  planner_workforce_runtime_changed: false
```
