# Task Card 07: Lifecycle Two-lane Gate Revalidation

## Identity

- task_id: `lifecycle-two-lane-gate-revalidation`
- campaign_id: `lifecycle-two-lane-canonical-closure`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- objective: Revalidate the full owner-authorized two-lane lifecycle plan against real Direct commits, real isolated Target success/cleanup, owner-finish archive closure, fault/retry actions, SLO telemetry, and external workspace disposition.
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Inputs and dependencies

- `tasks/lifecycle-two-lane-canonical-closure/INDEX.md`
- P0-P6 cards and commits listed in that index
- `/Users/jameschen/.codex/attachments/b09590a6-4abf-4c88-9ea6-656d2155800a/pasted-text-1.txt`
- Current canonical root, lifecycle state root, Target root, external MCP checkout, and salvage directory

## Allowed files

- `tasks/lifecycle-two-lane-canonical-closure/INDEX.md`
- `tasks/lifecycle-two-lane-canonical-closure/07-lifecycle-two-lane-gate-revalidation.md`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/self_hosted_mcp.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_mcp.py`
- `tests/engine/test_self_hosted_cli.py`

## Required behavior

1. Direct lane rejects lockfiles, generated/large changes, authority-sensitive flags, delegated workers, dirty roots, wrong branch, and concurrent mutation tasks; eligible Direct completion has an explicit preflight, scoped verification, staged-diff gate, and commit-bound receipt without Candidate/Target creation.
2. Ordinary primary-agent requests default to `DIRECT_CANONICAL`; callers must explicitly request `ISOLATED_TARGET` for governed Target execution.
3. Isolated lane rejects the disabled root, uses only `/Users/jameschen/Workspace/nexus-runtime-targets`, serializes one active slot, and preserves lazy read-only behavior.
4. `owner_finish` verifies binding, integrates, and archives the terminal receipt; mismatch or branch/verifier drift leaves approval and integration unmodified.
5. Integration failures expose a callable same-task integration retry; verified-uncommitted and dirty-retained cases expose one precise next action; duplicate Task Card hashes return the existing task and retry action without a second logical task.
6. Receipts expose separate provider, verifier, worktree, commit/hook, cleanup, wall, and overhead timing fields sufficient to calculate p95 SLOs.

## Verification commands

```bash
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'revalidation or direct or owner_finish or retry or fault'
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_mcp.py tests/engine/test_self_hosted_cli.py
git status --short --branch
git worktree list --porcelain
```

## Gate matrix

- 15 real Direct Lane commit cycles: `new_worktree_count=0`, no lifecycle Candidate, clean after each cycle.
- 10 real Isolated Target success cycles: one serial reusable slot, terminal cleanup, no active Target afterward.
- 5 fault/retry cycles: timeout, provider error, verifier failure, commit failure, integration failure; same task ID and one executable next action.
- Original-spec recheck: `test_original_gate_20_fault_retry_cases_keep_identity_and_one_action` passed for five fault classes × four repetitions.
- SLO p95: read <300ms, Direct overhead <1s, warm Target prepare/release <5s.
- P0 external disposition: disabled roots absent, MCP checkout clean, residue path/hash recorded, parent workspace guard present.

## Evidence

- Physical matrix: `test_revalidation_15_direct_10_isolated_5_fault_matrix` passed. It creates and verifies 15 real Direct commits, runs 10 real reusable serial Target prepare/commit/salvage/cleanup cycles, checks five executable fault actions, and asserts Direct overhead p95 <1s plus warm Target prepare/release p95 <5s.
- Original P4 gate: 20 bounded fault/retry cases passed with stable task IDs and exactly one recommended tool/next action per case.
- Default route regression: `test_ordinary_primary_request_defaults_to_direct_canonical` passed; an ordinary primary request returned a Direct handoff with no state or Target.
- Read SLO regression: `test_original_gate_read_p95_stays_below_300ms_without_side_effects` passed across 20 in-process read samples with no state-root creation.
- Focused action regression: Direct, owner-finish, retry, fault routing, and cleaned-verified retry tests passed; MCP/CLI suite passed `40 passed`; py_compile passed for all lifecycle surfaces.
- Commits: `48dbab1fa` (physical matrix), `957bc41f0` (cleaned verified block action routing), `bf57dcb54` (20 fault gate), `816aa5874` (Direct-by-default), `5d98bffeb` (CLI/MCP lane exposure), and `c41bcb00f` (read p95 gate).
- Live inventory: canonical checkout is clean on `nexus/integration/main`; one registered worktree (the canonical checkout); no active Target; disabled `nexus-worktrees` paths absent; empty runtime Target root removed.
- External disposition: `/Users/jameschen/Workspace/nexus-devspace-mcp` is clean on `nexus/mcp-tools-v1`; merged local branch `nexus/mcp-batch-1d-remediation-3` removed; residue preserved under `/Users/jameschen/Workspace/nexus-salvage/20260801-nexus-devspace-mcp`.

## Forbidden scope

No direct lifecycle JSON edits, no worker approval/integration, no push, no protected history rewrite, no deletion of branches/refs, no GitNexus forced directives, and no deletion of salvaged external residue.

## Exit criteria and residual debt

Complete only when every matrix row and SLO gate has physical receipt evidence, the canonical root and external MCP checkout are clean, no actionable orphan lacks owner disposition, and this card has a scoped commit. One pre-existing canonical `RETAINED_FOR_REVIEW` task remains owner-visible with an executable same-task retry surface; it was not mutated or silently archived because its `owner_decision` is null and its verified evidence permits—but does not authorize—a new attempt.
