# TASK-CODEX-DX-008-FEEDBACK — Map recurring failures to durable prevention seams

- **Campaign:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `COMPLETED`
- **Source spec:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source groups:** durable-feedback
- **Requirements:** REQ-010
- **Acceptance:** AC-010
- **Auto-chain:** `true`
- **Maximum claim:** prevention mapping
- **Depends on:** TASK-CODEX-DX-002-HISTORY; TASK-CODEX-DX-006-FIXTURES
- **Dependency unlock evidence:** accepted failure taxonomy receipt; accepted fixture smoke receipt
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `small`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Create a bounded machine-readable prevention registry and validator mapping every admitted recurring Codex failure class to exactly one current test, fixture, command, or instruction seam with owner and retirement condition.

## Observable outcome

recurring failures map to one prevention seam

## Non-goals

No recursive report, no routine-failure skill creation, no duplicate rule authority, no automatic learning promotion, and no claim about unavailable history.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-010 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-010 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |

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

- **Read:** docs/agents/LEARNING_WRITEBACK_OVERLAY.md; docs/benchmark/codex_dx_history_receipt_v1.schema.json; scripts/bench/codex_dx_history.py; scripts/ci/run_swebench_subset.py; tests/benchmark/test_ci_swebench_subset.py
- **Edit:** none
- **Create:** configs/codex_dx_failure_prevention.json; scripts/ops/validate_codex_dx_failure_prevention.py; tests/ops/test_codex_dx_failure_prevention.py
- **Delete:** none
- **Maximum touched production files:** 2
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** Repeated setup, fixture, command, environment, secret, convention, and context failures are evidenced, but no bounded prevention mapping exists.
- **Assumptions requiring verification:** Only recurring, evidenced classes are admitted; one primary prevention seam can own each class.
- **Architecture risks:** The registry could become a parallel learning or policy authority.
- **Evidence risks:** Narrative-only or duplicate mappings may look complete without a physical guard.
- **Missing owner decision:** none

## Mandatory source audit

Read the learning write-back overlay, accepted history receipt, fixture smoke receipt, and all mapped test/command/index identities. Exclude unsupported or one-off categories.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Add duplicate, missing-owner, nonexistent-path, narrative-only, and no-retirement fixtures and prove validation fails.

## Implementation constraints

Registry is navigation/evidence only; preserve existing learning authority; require stable IDs, evidence refs, one primary prevention seam, owner, status, and removal condition.

## GREEN and regression gates

Every admitted recurring class maps to one existing prevention seam; duplicates, missing paths, unsupported claims, and unowned entries fail.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_codex_dx_failure_prevention.py | Validate prevention registry behavior and negative controls. | All selected tests pass. |
| C2 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 scripts/ops/validate_codex_dx_failure_prevention.py configs/codex_dx_failure_prevention.json | Validate the canonical registry. | Exit 0 with exact counts. |
| C3 | TARGET_ROOT | git diff --check | Check scoped patch whitespace. | Exit 0 with no findings. |

## Physical evidence

Bind source spec SHA, Task Card SHA, attempt identity, Target root, starting and final HEAD, complete diff, changed symbols, command outputs, verifier identities, and terminal state. Preserve fixture, canary, benchmark, and source evidence as distinct layers. Missing evidence fails closed.

## Independent review

A fresh reviewer must compare the approved specification, this card, complete scoped diff, RED/GREEN evidence, command outputs, benchmark or schema receipts, unrelated-state audit, and authority boundaries. Review cannot approve or integrate the Candidate.

## Exit conditions

- **PASS:** Registry, validator, tests, and scoped Candidate evidence pass without adding authority or speculative entries.
- **BLOCK:** Any mapping lacks physical evidence, duplicates authority, references nonexistent paths, or claims unavailable history.
- **Residual debt:** New classes require future recurrence evidence and owner-governed admission.
- **Next gate:** Independent Candidate acceptance supplies the prevention receipt required by the after benchmark.
