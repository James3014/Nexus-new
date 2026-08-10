# TASK-CODEX-DX-005-TESTS — Converge canonical repository test commands

- **Campaign:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `ACTIVE`
- **Source spec:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source groups:** test-contract
- **Requirements:** REQ-005
- **Acceptance:** AC-005
- **Auto-chain:** `true`
- **Maximum claim:** command truth
- **Depends on:** TASK-CODEX-DX-004-BOOTSTRAP
- **Dependency unlock evidence:** accepted core setup and doctor command contract
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

Create one canonical test command entrypoint and harden fast/changed commands so environment, fast, impacted, full, lint, and fixture tiers are explicit and fail truthfully.

## Observable outcome

isolated canonical command canary

## Non-goals

No test weakening, no baseline deletion, no empty success, no automatic fix, no full-suite success claim from focused tests, and no CI redesign beyond command parity.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-005 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-005 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |

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

- **Read:** scripts/ops/test_fast.sh; scripts/ops/test_changed.sh; scripts/ops/select_tests.py; docs/testing/test_runbook.md; .github/workflows/pytest.yml; .github/workflows/lint.yml; tests/core; tests/services/test_policy_gate.py
- **Edit:** scripts/ops/test_fast.sh; scripts/ops/test_changed.sh
- **Create:** scripts/ops/test_repo.sh; tests/ops/test_repo_test_commands.py
- **Delete:** none
- **Maximum touched production files:** 0
- **Maximum touched test files:** 4

## Unknown scan

- **Known facts:** Fast and changed scripts exist, but there is no single command matrix; changed selection uses shell word splitting and docs expose conflicting commands.
- **Assumptions requiring verification:** One shell entrypoint can dispatch stable modes without becoming a test-selection authority beyond existing select_tests.py.
- **Architecture risks:** A wrapper could hide selected targets or weaken CI semantics.
- **Evidence risks:** Empty Ruff/test selections or missing paths may return zero and create false green.
- **Missing owner decision:** none

## Mandatory source audit

Inspect existing scripts, selector, testing runbook, pytest/lint workflows, and focused target existence. Preserve CI/full command semantics.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Exercise no-path, missing-path, empty-selection, failing-test, and deleted-file cases and record any silent success or ambiguous target selection.

## Implementation constraints

Use arrays rather than unsafe word splitting, print selected targets, preserve exit codes, support documented modes only, and require explicit escalation to full tests.

## GREEN and regression gates

All modes resolve exact commands; missing/empty inputs follow documented fail/fallback behavior; command contract tests and shell syntax pass.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_repo_test_commands.py tests/services/test_policy_gate.py | Validate canonical command behavior. | All selected tests pass. |
| C2 | TARGET_ROOT | bash -n scripts/ops/test_repo.sh scripts/ops/test_fast.sh scripts/ops/test_changed.sh | Validate shell syntax. | Exit 0. |
| C3 | TARGET_ROOT | bash scripts/ops/test_repo.sh fast | Run canonical fast canary. | Exit 0 with selected targets printed. |
| C4 | TARGET_ROOT | git diff --check | Check scoped patch whitespace. | Exit 0 with no findings. |

## Physical evidence

Bind source spec SHA, Task Card SHA, attempt identity, Target root, starting and final HEAD, complete diff, changed symbols, command outputs, verifier identities, and terminal state. Preserve fixture, canary, benchmark, and source evidence as distinct layers. Missing evidence fails closed.

## Independent review

A fresh reviewer must compare the approved specification, this card, complete scoped diff, RED/GREEN evidence, command outputs, benchmark or schema receipts, unrelated-state audit, and authority boundaries. Review cannot approve or integrate the Candidate.

## Exit conditions

- **PASS:** Canonical command matrix, hardened fast/changed scripts, tests, canary, commit, and Candidate evidence pass.
- **BLOCK:** Any required mode is silently empty, paths are guessed, focused tests are called full proof, or setup contract is bypassed.
- **Residual debt:** Subsystem-specific commands remain in nearest authority files and may be added to the context index later.
- **Next gate:** Independent Candidate acceptance unlocks deterministic fixture smoke repair.
