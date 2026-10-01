# Issue #973 — External Candidate adoption bridge R5

This Card authorizes lifecycle re-entry of the same immutable governed Candidate after R4
was canonically cancelled. R4 proved the clean-target verifier environment and reached
lifecycle-native verification, but the authority-sensitive Runtime Recovery diff remained
hard-blocked because the tracked adoption Card projected no
`repository-authority-change.v1` marker. `TASK-EPB-004-R1`, integrated at
`a6fb63937191c18a1d937a606c45eb0ecb1ddc7b`, repairs only that re-entry seam: the physically
hashed Card can now project this one existing marker into the canonical Repository Contract
Gate, which converts the authority-sensitive finding to `approval_required` and still
requires exact Owner Architecture Approval.

R1/R2/R3/R4 history remains immutable and terminal; none may be retried or overwritten.
This Card does not authorize implementation changes, Candidate rewrite, runtime activation,
approval, integration, release, or production claims.

task_id: `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R5`
attempt_id: `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R5-ADOPT-1`
execution_lane: `GOVERNED`
issue_number: `973`
source_task_card: `tasks/github-issue-973-runtime-recovery-governed-20260923/00-runtime-recovery-one-shot-consumer.md`
source_candidate: `3d88a614c27e0c21a15c68dc70dc3d2193084cee`
source_base: `5e35d4fbfbf5df147a847c7dcf84fefbb7f5f471`
prior_adoption_task: `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R4`
prior_adoption_disposition: `CANCELLED`
authority_marker_reentry_task: `TASK-EPB-004-R1`
authority_marker_reentry_commit: `a6fb63937191c18a1d937a606c45eb0ecb1ddc7b`
independent_review_artifact_sha256: `ec602688d26be1e69f3de7f16e21ca4016431c420845cc34e849821e2d61dca0`

`AUTO_CHAIN=false`

## Allowed repository paths

- `nexus/contracts/break_glass_recovery.py`
- `nexus/orchestrator/break_glass_recovery.py`
- `scripts/ops/break_glass_recovery.py`
- `tests/contracts/test_break_glass_recovery_contract.py`
- `tests/nexus/orchestrator/test_break_glass_recovery.py`
- `docs/specs/NEXUS_BREAK_GLASS_RECOVERY_001.md`
- `docs/governance/rollback_runbook.md`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`

## Forbidden scope

- `scripts/ops/mcp_gateway_durable.py`
- `nexus/contracts/gateway_deployment.py`
- `tasks/**`

## Protected contracts

- `repository-authority-change.v1`

## Exact verification commands

- `uv sync --all-groups --all-extras`
- `uv run pytest -q tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
- `uv run pytest -q tests/ops/test_bootstrap_authority_files.py::test_external_bootstrap_recovery_boundary_is_fail_closed`
- `uv run ruff check nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
- `uv run ruff format --check --preview nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
- `uv run python -m py_compile nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py`
- `git diff --check`

## Re-entry invariants

- Candidate/base/tree/diff/review identities remain identical to the independently reviewed
  governed Candidate; R5 does not create or rewrite a Candidate.
- R1/R2/R3/R4 tasks remain immutable terminal history and are not retry authority.
- The exact `repository-authority-change.v1` marker is derived from this physically hashed
  Card and only changes the existing Repository Contract Gate result from hard-block to
  `approval_required`; it grants no approval itself.
- The first verifier command restores the original Task Card's clean-target dependency
  bootstrap. It may create only ignored local verification environment/cache material; it
  does not authorize source edits or Candidate changes.
- A detached clean worktree at exact Candidate `3d88a614...` physically ran this exact seven-
  command verifier sequence before this Card was tracked: environment bootstrap succeeded,
  69/69 break-glass tests passed, 1/1 bootstrap boundary passed, Ruff/format/py_compile and
  `git diff --check` passed, and Git remained clean.
- R5 requires a fresh one-shot `CANDIDATE_ADOPT_EXTERNAL` authority bound to the live Gateway
  server, controller revision, this Task Card hash, task/attempt, immutable Candidate, and
  existing independent-review evidence.
- The bridge may invoke lifecycle-native Candidate verification only; worker invocations
  remain zero.
- Adoption stops at `PENDING_HUMAN_APPROVAL`; approval and integration are separate Owner
  actions.
- Runtime activation of the #973 break-glass consumer remains outside this Card.
