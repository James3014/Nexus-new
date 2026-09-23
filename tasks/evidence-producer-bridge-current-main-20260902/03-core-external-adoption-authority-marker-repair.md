# TASK-EPB-004-R1 — External Candidate Authority-Marker Re-entry Repair

task_id: `TASK-EPB-004-R1`

- Campaign: `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`
- Mission: `CORE-EVIDENCE-TRUST-CANONICALIZATION-20260902`
- Status: `ACTIVE`
- Trigger: governed Issue #973 external Candidate R4 lifecycle verification
- Trigger task: `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R4`
- Trigger Candidate: `3d88a614c27e0c21a15c68dc70dc3d2193084cee`
- Exact repair base: `9dccc89972b169e0ec676db49a27795654fbc801`
- Execution lane: `GOVERNED`
- Commit/Candidate required: `true`
- Parallel safe: `false`

## Goal

Repair the existing external-Candidate adoption bridge so a tracked immutable adoption Card
can carry the repository's existing `repository-authority-change.v1` marker into the
lifecycle-native `ArchitectTaskContract`. Preserve the current Repository Contract Gate:
the marker converts an authority-sensitive Candidate from hard-blocked to
`approval_required`; it must never bypass exact Owner Architecture Approval.

## Required invariants

1. The marker is derived only from the physically hashed tracked adoption Card; callers may
   not mint it independently through the public request.
2. Historical adoption Cards without a marker remain byte/behavior compatible and continue
   deriving `protected_contracts=[]`.
3. The only marker accepted by this repair parser is `repository-authority-change.v1`.
   Unknown/duplicate/malformed marker sections fail closed as
   `ADOPTION_CARD_CONTRACT_UNRESOLVABLE`.
4. External adoption requires request `protected_contracts` to exactly equal the Card-derived
   projection; omission/substitution/widening fails before Target verification.
5. `CandidateVerifier` and `RepositoryContractGate` remain canonical. No duplicate verifier,
   approval path, or route authority is introduced.
6. A marked authority-sensitive Candidate reaches lifecycle verification with
   `authority_change_required=true` and a deterministic `authority_findings_sha256`; it still
   stops at `PENDING_HUMAN_APPROVAL` and requires exact Architecture Approval before any
   integration.
7. No Candidate rewrite, worker call, approval, integration, merge, runtime activation,
   release, production, or public claim is performed by this source task.

## Allowed paths

- `nexus/contracts/lifecycle_action.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/contracts/test_lifecycle_action.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

Maximum changed paths: `4`; deletions: `0`.

## Forbidden scope

- `nexus/orchestrator/repository_contract_gate.py`
- `nexus/orchestrator/candidate_verifier.py`
- `nexus/orchestrator/worktree_manager.py`
- Gateway process/recovery source
- #973 Runtime Recovery Candidate source
- approval/integration semantics outside exact existing Architecture Approval flow
- new marker kinds, generic protected-contract import, standing-grant widening, release or production effects

## Required RED / hostile witnesses

- A tracked adoption Card declaring `repository-authority-change.v1` currently cannot project
  the marker and an authority-sensitive external Candidate fails with
  `effective_route_authority_change:*`.
- Card-derived marker + request marker succeeds to lifecycle-native verification and projects
  `authority_change_required=true` without granting approval.
- Caller marker absent from Card, Card marker absent from request, unknown marker, duplicate
  marker section, malformed bullet, and marker tamper all fail closed before promotion.
- Existing unmarked adoption Card fixtures continue to parse and adopt unchanged.

## Verification

- `uv run pytest -q tests/contracts/test_lifecycle_action.py`
- `uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'external_candidate_adoption or adoption_card or authority'`
- `uv run ruff check nexus/contracts/lifecycle_action.py nexus/orchestrator/self_hosted_task_service.py tests/contracts/test_lifecycle_action.py tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `uv run pyright nexus/contracts/lifecycle_action.py nexus/orchestrator/self_hosted_task_service.py`
- `git diff --check`

## Exit and claim ceiling

Independent acceptance must bind exact base/head/tree/Card hash, complete four-path maximum
diff, hostile marker-substitution controls, backwards compatibility, and proof that the
existing Architecture Approval gate remains required.

Maximum claim:

`EXTERNAL_ADOPTION_AUTHORITY_MARKER_REENTRY_CANDIDATE_VERIFIED`

No #973 Candidate acceptance, approval, integration, merge, runtime activation, release, or
production claim is granted by this Task.

`AUTO_CHAIN=false`
