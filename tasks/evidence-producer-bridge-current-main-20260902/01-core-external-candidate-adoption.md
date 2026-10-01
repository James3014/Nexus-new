# TASK-EPB-002-R1 — Current-main Core External Candidate Adoption

task_id: `TASK-EPB-002-R1`

- Campaign: `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`
- Mission: `CORE-EVIDENCE-TRUST-CANONICALIZATION-20260902`
- Status: `ACTIVE`
- Source spec: `SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001`
- Source spec SHA-256: `9e841f43d63ffc10704f00b4d21b88f9fbf78f3a473839a1409f278a951251a1`
- Requirements: `REQ-002; REQ-003; REQ-004; REQ-005; REQ-006`
- Acceptance: `AC-002; AC-003; AC-005; AC-006; AC-007`
- Exact base commit: `6ee715d6bf969c58ed0ceb840deaa70ba5434243`
- Exact base tree: `a92a4c56a3ba58c8cb238f0870dace209d66be00`
- Evidence Trust predecessor: `EVIDENCE_TRUST_FOUNDATION_INTEGRATED_SOURCE_VERIFIED`
- Historical core donor: commit `913a90900b906f31d18e35efdd853863aad92400`; pattern/reference only.
- Execution lane: `GOVERNED`
- Commit/Candidate required: `true`
- Parallel safe: `false`

## Goal

Add the current-main-native core lifecycle seam that physically re-verifies one
exact immutable precommitted external Candidate and atomically forms ordinary
`PENDING_HUMAN_APPROVAL` state, without a worker call, Candidate rewrite,
approval, integration, push, release, or production effect.

## Required invariants

1. Exact Candidate/base/tree/diff/card/evidence identities are recomputed from
   physical source; caller prose is not authority.
2. The existing `CandidateVerifier`, `CandidateCommitter`, lifecycle state, and
   Target/lease owners remain canonical; no duplicate verifier/state machine.
3. Adoption calls no implementation provider and never rewrites the Candidate.
4. State is reserved/finalized atomically; partial failure creates no promotable
   state.
5. Exact replay returns the original receipt; any identity/input drift fails.
6. Timeout/unknown outcome reconciles durable state before retry.
7. The terminal boundary is pending approval only.

## Allowed paths

- `nexus/contracts/lifecycle_action.py`
- `nexus/orchestrator/candidate_commit.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/worktree_manager.py`
- `tests/contracts/test_lifecycle_action.py`
- `tests/nexus/orchestrator/test_candidate_commit.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`

Maximum changed paths: `8`; deletions: `0`.

## Forbidden scope

- Gateway, CLI, public adoption action, standing-grant, Product/Evidence Trust,
  Planner/Workforce, provider/worker, approval/integration, GitHub, release,
  runtime activation, production, Task4, signing, or public claims.
- Caller-minted verified receipt/state, generic trust-SHA import, Candidate
  patch/rebase/squash/cherry-pick/wrapper/replacement.

## Required RED

Before implementation, tests must prove current main lacks the typed core
adoption request/service and that the intended positive path fails for missing
behavior rather than fixture/import defects.

## Hostile witnesses

- Candidate/base/tree/diff/card/evidence substitution, path escape, symlink.
- worker dispatch or Candidate mutation count non-zero.
- existing task collision, concurrent reservation, replay drift.
- fault after reservation and before finalize; interrupted `ADOPTING` replay.
- caller-supplied state/receipt; missing verifier evidence.
- approval/integration/downstream fields or effects.

## Verification

- `uv run pytest -q tests/contracts/test_lifecycle_action.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_worktree_manager.py`
- `uv run ruff check nexus/contracts/lifecycle_action.py nexus/orchestrator/candidate_commit.py nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/worktree_manager.py tests/contracts/test_lifecycle_action.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_worktree_manager.py`
- `uv run pyright nexus/contracts/lifecycle_action.py nexus/orchestrator/candidate_commit.py nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/worktree_manager.py`
- `git diff --check`

## Exit and claim ceiling

Independent acceptance must bind exact base/head/tree/card hash, complete diff,
deletions, positive physical witness, hostile replay/fault controls, and zero
worker/downstream effect.

Maximum claim:

`CORE_EXTERNAL_CANDIDATE_ADOPTION_CANDIDATE_VERIFIED`

No public action, approval, integration, merge, release, production, Task4, or
runtime-loaded claim.

`AUTO_CHAIN=false`
