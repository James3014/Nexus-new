# TASK-CODEX-DX-001-BEFORE — Freeze the immutable before benchmark arm

- **Campaign:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `ACTIVE`
- **Source spec:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source groups:** paired-benchmark
- **Requirements:** REQ-008
- **Acceptance:** AC-008
- **Auto-chain:** `false`
- **Maximum claim:** paired benchmark evidence only
- **Depends on:** none
- **Dependency unlock evidence:** none
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Create the versioned Codex DX benchmark manifest, receipt schema, deterministic aggregator, and tests; then run the immutable before arm against code baseline b6601270e before any product-facing improvement.

## Observable outcome

immutable before-arm receipt bound to b6601270e

## Non-goals

No setup, instruction, skill, fixture, CI, or documentation improvement; no after-arm run; no lift, production, approval, integration, or public claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-008 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-008 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |

## Owner decisions

DEC-001 defines the full Codex DX product outcome. DEC-003 authorizes continued work with incomplete history explicitly labeled. DEC-004 requires a clean isolated governed Target. No worker approval, integration, push, cleanup, or production authority is granted.

## Source and start state

- **Workspace/root:** /private/tmp/nexus-codex-dx-019fe8e1
- **Branch:** codex/codex-dx-reliability
- **Starting HEAD:** b6601270edd95a756c4eab8c7a623006ee1b32d1
- **Dirty baseline:** clean at Target creation; only the approved source specification and campaign authority bundle may be published before task execution
- **Required initial verification:** Verify root, branch, HEAD, status, worktrees, source spec digest, campaign index, and exact card hash before mutation.
- **Freshness rule:** Re-read after HEAD, index, worktree, transport, source spec, or card hash changes.

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

- **Read:** tasks/SPEC-CODEX-DX-RELIABILITY-20260810.md; tasks/codex-dx-reliability-20260810/INDEX.md; scripts/bench/public_benchmark_manifest.schema.json; scripts/bench/public_benchmark_pilot_v1.json; scripts/bench/fixture_materialization.py; tests/benchmark/test_fixture_materialization.py; scripts/ci/run_swebench_subset.py; README.md; AGENTS.md
- **Edit:** none
- **Create:** docs/benchmark/codex_dx_benchmark_receipt_v1.schema.json; configs/benchmarks/codex_dx_before_v1.json; scripts/bench/codex_dx_benchmark.py; tests/benchmark/test_codex_dx_benchmark.py
- **Delete:** none
- **Maximum touched production files:** 3
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** Current smoke runner is 0/5 because the root shell runner is absent; Codex task-history transport is unavailable; canonical code baseline is immutable b6601270e.
- **Assumptions requiring verification:** Three independent fresh Luna/Codex contexts can execute each of five task classes without inheriting repository solution context.
- **Architecture risks:** The benchmark harness must remain an observer and receipt producer, not a route, verifier, or runtime authority.
- **Evidence risks:** Reused context, mutable fixtures, arm-specific prompts, or process-exit-only scoring would invalidate the comparison.
- **Missing owner decision:** none

## Mandatory source audit

Read the public benchmark manifest/schema, fixture materialization contract, current 0/5 runner, context-budget tests, and root authority. Verify all five task classes have identical before/after semantics and task-specific verifiers.

## Start-state classification

`PREEXISTING_BASELINE_FAILURE`

## RED or existing-guard proof

Record the existing 0/5 smoke failure and demonstrate that no versioned Codex DX receipt can currently bind fresh session, context cost, human intervention, diff scope, and verifier outcome.

## Implementation constraints

The harness must target immutable source snapshots, emit complete per-trial identities, keep benchmark code outside the subject baseline, use no provider secrets, and invalidate incomplete trials. It must not modify b6601270e.

## GREEN and regression gates

Schema and aggregator tests pass; the manifest freezes five task classes and three repetitions; 15 before trials are receipt-bound or explicitly invalid; the immutable baseline and all failed setup/context/test paths remain visible.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | python3 scripts/ci/run_swebench_subset.py --mode smoke --output /tmp/codex-dx-before-smoke.jsonl --timeout 1 | Reproduce the existing smoke baseline. | Exit 1 with five missing-runner case errors recorded. |
| C2 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/benchmark/test_codex_dx_benchmark.py tests/benchmark/test_fixture_materialization.py | Validate benchmark schema, identity, invalidation, and fixtures. | All selected tests pass. |
| C3 | TARGET_ROOT | git diff --check | Check scoped patch whitespace. | Exit 0 with no findings. |

## Physical evidence

Bind source spec SHA, Task Card SHA, attempt identity, Target root, starting and final HEAD, complete diff, changed symbols, command outputs, verifier identities, and terminal state. Preserve fixture, canary, benchmark, and source evidence as distinct layers. Missing evidence fails closed.

## Independent review

A fresh reviewer must compare the approved specification, this card, complete scoped diff, RED/GREEN evidence, command outputs, benchmark or schema receipts, unrelated-state audit, and authority boundaries. Review cannot approve or integrate the Candidate.

## Exit conditions

- **PASS:** Versioned harness and tests pass, 15-trial before receipt set is bound to b6601270e, scoped commit exists, and Candidate evidence is pending independent acceptance.
- **BLOCK:** Fresh contexts cannot be isolated, the baseline changes, any trial lacks identity/verifier/context/intervention data, or required commit/Candidate evidence fails.
- **Residual debt:** Codex app history remains a separate TASK-CODEX-DX-002-HISTORY responsibility.
- **Next gate:** Independent Candidate acceptance, then select exactly one successor card.
