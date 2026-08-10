# TASK-CODEX-DX-006-FIXTURES — Repair deterministic fixture-backed smoke benchmarking

- **Campaign:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source groups:** fixture-benchmark
- **Requirements:** REQ-006
- **Acceptance:** AC-006
- **Auto-chain:** `false`
- **Maximum claim:** fixture smoke 5/5
- **Depends on:** TASK-CODEX-DX-005-TESTS
- **Dependency unlock evidence:** accepted canonical test command contract
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

Replace the missing root shell-runner dependency with a checked-in deterministic case runner, materialized fixtures, truthful per-case verifiers, and CI parity.

## Observable outcome

five deterministic smoke cases with negative control

## Non-goals

No live model/provider benchmark, no secrets requirement for smoke, no process-exit-only health score, no production capability claim, and no unbounded SWE-bench expansion.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-006 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-006 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |

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

- **Read:** scripts/ci/run_swebench_subset.py; scripts/ci/smoke_cases.json; scripts/bench/fixture_materialization.py; tests/benchmark/test_fixture_materialization.py; .github/workflows/benchmark-ci.yml; scripts/bench/public_benchmark_manifest.schema.json
- **Edit:** scripts/ci/run_swebench_subset.py; scripts/ci/smoke_cases.json; scripts/bench/fixture_materialization.py; .github/workflows/benchmark-ci.yml; tests/benchmark/test_fixture_materialization.py
- **Create:** scripts/ci/run_benchmark_case.py; tests/benchmark/test_ci_swebench_subset.py
- **Delete:** none
- **Maximum touched production files:** 5
- **Maximum touched test files:** 2

## Unknown scan

- **Known facts:** The current five smoke cases all error because nexus_benchmark.sh is absent; workflow injects Gemini/OpenAI secrets and uses Python 3.11.
- **Assumptions requiring verification:** Five deterministic fixtures can exercise runner, setup, patch, verifier, and receipt seams without provider calls.
- **Architecture risks:** A fixture runner could be confused with live SWE-bench or Nexus production performance.
- **Evidence risks:** Synthetic health based on exit code or missing hidden verifiers could create false green.
- **Missing owner decision:** none

## Mandatory source audit

Inspect current subset runner, case list, fixture materialization and path-escape tests, benchmark workflow, and public manifest contract. Confirm each case has a deterministic verifier.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Reproduce 0/5 missing-runner errors and add negative cases for missing fixture, path escape, missing verifier, timeout, and false-zero exit.

## Implementation constraints

Use Python 3.12 parity, no core secrets, checked-in fixtures or deterministic materialization, explicit case verifier output, bounded artifacts, and fail-closed aggregation.

## GREEN and regression gates

Smoke is 5/5 through the checked-in runner; each case binds fixture and verifier hashes; every negative control returns non-zero and correct classification; CI invokes the same command.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/benchmark/test_ci_swebench_subset.py tests/benchmark/test_fixture_materialization.py | Validate runner, fixtures, verifiers, and negative controls. | All selected tests pass. |
| C2 | TARGET_ROOT | python3 scripts/ci/run_swebench_subset.py --mode smoke --output /tmp/codex-dx-fixture-smoke.jsonl --timeout 30 | Run deterministic smoke canary. | Exit 0 with five of five verifier passes. |
| C3 | TARGET_ROOT | git diff --check | Check scoped patch whitespace. | Exit 0 with no findings. |

## Physical evidence

Bind source spec SHA, Task Card SHA, attempt identity, Target root, starting and final HEAD, complete diff, changed symbols, command outputs, verifier identities, and terminal state. Preserve fixture, canary, benchmark, and source evidence as distinct layers. Missing evidence fails closed.

## Independent review

A fresh reviewer must compare the approved specification, this card, complete scoped diff, RED/GREEN evidence, command outputs, benchmark or schema receipts, unrelated-state audit, and authority boundaries. Review cannot approve or integrate the Candidate.

## Exit conditions

- **PASS:** Five-case smoke and negative controls pass, workflow parity is static-checked, and scoped commit/Candidate evidence is formed.
- **BLOCK:** Any case needs provider secrets/network, fixture identity is missing, verifier truth is absent, or workflow and local commands diverge.
- **Residual debt:** Lite/live provider benchmarks remain separately governed and cannot inherit this smoke claim.
- **Next gate:** Independent Candidate acceptance unlocks docs convergence and durable feedback.
