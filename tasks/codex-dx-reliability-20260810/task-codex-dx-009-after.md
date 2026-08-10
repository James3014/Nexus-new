# TASK-CODEX-DX-009-AFTER — Run the immutable after arm and paired acceptance

- **Campaign:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source groups:** paired-benchmark
- **Requirements:** REQ-008; REQ-009
- **Acceptance:** AC-008; AC-009
- **Auto-chain:** `false`
- **Maximum claim:** paired benchmark evidence only
- **Depends on:** TASK-CODEX-DX-002-HISTORY; TASK-CODEX-DX-003-CONTEXT; TASK-CODEX-DX-004-BOOTSTRAP; TASK-CODEX-DX-005-TESTS; TASK-CODEX-DX-006-FIXTURES; TASK-CODEX-DX-007-DOCS; TASK-CODEX-DX-008-FEEDBACK
- **Dependency unlock evidence:** accepted history coverage receipt; accepted context index receipt; accepted setup canary receipt; accepted test command receipt; accepted fixture smoke receipt; accepted docs audit receipt; accepted prevention mapping receipt
- **Task type:** `INTEGRATION_VERIFY`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `false`
- **Candidate required:** `false`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Run 15 independent fresh-session after trials against the accepted candidate snapshot, validate every receipt, and compare with the immutable before arm without changing benchmark tasks or verifiers.

## Observable outcome

immutable after arm and paired comparison receipt

## Non-goals

No implementation repair during trials, no session reuse, no human rescue counted as pass, no threshold relaxation, no approval/integration/push/release, and no production/public claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-008 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| REQ-009 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-008 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-009 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |

## Owner decisions

DEC-001 defines the full Codex DX product outcome. DEC-003 authorizes continued work with incomplete history explicitly labeled. DEC-004 requires a clean isolated governed Target. No worker approval, integration, push, cleanup, or production authority is granted.

## Source and start state

- **Workspace/root:** REVERIFY_AFTER_DEPENDENCY
- **Branch:** REVERIFY_AFTER_DEPENDENCY
- **Starting HEAD:** REVERIFY_AFTER_DEPENDENCY
- **Dirty baseline:** REVERIFY_AFTER_DEPENDENCY
- **Required initial verification:** Re-read root, branch, HEAD, status, worktrees, source spec digest, campaign index, and this active card after dependency acceptance.
- **Freshness rule:** Re-read after every dependency acceptance, HEAD change, reconnect, or dirty-state change.

## MCP execution profile

- **App/server and action snapshot:** not applicable
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** not applicable
- **Reconnect reconciliation:** not applicable
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner-approved source specification and campaign frontier.
- **Execution authority:** This exact Git-tracked card in the clean isolated Target through repository-owned local governed execution.
- **Verification authority:** Exact command manifest, source acceptance criteria, and independent reviewer.
- **Receipt authority:** Commit-bound Task Card evidence and benchmark/schema receipts named below.
- **Approval/integration authority:** Owner only; implementer and reviewer cannot approve, integrate, push, merge, release, or clean up.

## Allowed scope

- **Read:** tasks/SPEC-CODEX-DX-RELIABILITY-20260810.md; tasks/codex-dx-reliability-20260810/INDEX.md; docs/benchmark/codex_dx_benchmark_receipt_v1.schema.json; configs/benchmarks/codex_dx_before_v1.json; scripts/bench/codex_dx_benchmark.py; docs/benchmark/codex_dx_history_receipt_v1.schema.json; configs/codex_task_context_index.json; scripts/ops/repo_doctor.py; scripts/ops/test_repo.sh; scripts/ci/run_swebench_subset.py; configs/codex_dx_failure_prevention.json
- **Edit:** none
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 0
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** The source acceptance requires 15 of 15 verified after passes, zero human interventions, zero secret reads, zero unauthorized/destructive actions, and no median context-byte increase.
- **Assumptions requiring verification:** All dependency Candidates have independent acceptance and one immutable candidate snapshot can be frozen for the after arm.
- **Architecture risks:** Aggregation could accidentally promote benchmark evidence into production or approval truth.
- **Evidence risks:** Missing task history, incomplete metrics, different prompts/fixtures, or implementer self-scoring invalidates comparison.
- **Missing owner decision:** none

## Mandatory source audit

Re-read every accepted dependency receipt, freeze candidate source and benchmark identities, verify fresh-session isolation, and independently validate task-specific verifiers before aggregation.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Inject one false pass, reused session, missing metric, human intervention, secret read, changed fixture, and context regression; each must invalidate or fail the paired result.

## Implementation constraints

No mutation during trials, identical task semantics and verifier hashes across arms, complete invalid-trial accounting, independent aggregation, and claim ceiling limited to paired benchmark evidence.

## GREEN and regression gates

Thirty total trials are comparable; after is 15/15 with zero prohibited events and no median context-byte increase; every trial and aggregate receipt validates.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/benchmark/test_codex_dx_benchmark.py tests/benchmark/test_codex_dx_history.py tests/ops/test_codex_dx_failure_prevention.py | Validate benchmark, history, and prevention receipt contracts. | All selected tests pass. |
| C2 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 scripts/bench/codex_dx_benchmark.py compare --before configs/benchmarks/codex_dx_before_v1.json --after /tmp/codex-dx-after-v1.json | Aggregate immutable paired receipts. | Exit 0 only when all source thresholds pass. |
| C3 | TARGET_ROOT | git diff --check | Confirm verification created no repository diff. | Exit 0 with no findings. |

## Physical evidence

Bind source spec SHA, Task Card SHA, attempt identity, Target root, starting and final HEAD, complete diff, changed symbols, command outputs, verifier identities, and terminal state. Preserve fixture, canary, benchmark, and source evidence as distinct layers. Missing evidence fails closed.

## Independent review

A fresh reviewer must compare the approved specification, this card, complete scoped diff, RED/GREEN evidence, command outputs, benchmark or schema receipts, unrelated-state audit, and authority boundaries. Review cannot approve or integrate the Candidate.

## Exit conditions

- **PASS:** After and paired receipts validate every threshold; independent reviewer reports bounded benchmark evidence and no repository mutation.
- **BLOCK:** Any dependency is unaccepted, task history remains incomplete, source/fixture/verifier identities differ, a threshold fails, or any trial lacks complete evidence.
- **Residual debt:** General production effectiveness and unobserved future tasks remain outside the claim.
- **Next gate:** Owner acceptance decision; no automatic integration, push, release, or cleanup.
