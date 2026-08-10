# TASK-CODEX-DX-003-CONTEXT — Add the canonical bounded Codex context contract

- **Campaign:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `ACTIVE`
- **Source spec:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source groups:** context-contract
- **Requirements:** REQ-002
- **Acceptance:** AC-002
- **Auto-chain:** `true`
- **Maximum claim:** bounded retrieval correctness
- **Depends on:** TASK-CODEX-DX-001-BEFORE
- **Dependency unlock evidence:** accepted immutable before-arm context-cost receipt
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

Add one machine-readable task-to-authority/context/test index, a fail-closed validator, focused tests, and compact AGENTS/skill consumption without creating a second router.

## Observable outcome

one validated task-to-context index

## Non-goals

No full-corpus index, no route/workforce/lifecycle authority change, no new broad narrative report, and no removal of existing safety gates.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-002 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-002 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |

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

- **Read:** AGENTS.md; .agents/skills/nexus-task-launch/SKILL.md; tasks/bootstrap-authority-convergence/09-context-budget-and-overlay-gates.md; tests/ops/test_bootstrap_context_budget.py; tests/ops/test_nexus_enforced_briefing.py; docs/agents/TASK_EXECUTION_CONTRACT.md
- **Edit:** AGENTS.md; .agents/skills/nexus-task-launch/SKILL.md
- **Create:** configs/codex_task_context_index.json; scripts/ops/validate_codex_context_index.py; tests/ops/test_codex_task_context_index.py
- **Delete:** none
- **Maximum touched production files:** 4
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** Root authority already requires targeted retrieval, but no machine-readable task mapping exists; broad surface is about 6.9 MB.
- **Assumptions requiring verification:** A small stable task taxonomy covers the five benchmark task classes without duplicating dynamic repository truth.
- **Architecture risks:** The index could accidentally become a second router or stale source of current runtime truth.
- **Evidence risks:** Line-count reduction alone could appear successful while semantic authority or test mapping is lost.
- **Missing owner decision:** none

## Mandatory source audit

Read root authority, task execution contract, bootstrap context-budget card/tests, and the task-launch skill. Inventory only current paths used by the benchmark task classes.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Delete or corrupt a representative test mapping in a fixture and prove the validator fails rather than scanning broad docs or guessing.

## Implementation constraints

Keep root AGENTS compact, preserve authority precedence, use existing paths only, validate schema and path existence, and expose no mutation authority.

## GREEN and regression gates

Every benchmark task resolves one authority path, bounded context set, test command, fixture policy, and forbidden scope; missing paths and duplicate authorities fail.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_codex_task_context_index.py tests/ops/test_bootstrap_context_budget.py tests/ops/test_nexus_enforced_briefing.py | Validate mapping semantics and context-budget invariants. | All selected tests pass. |
| C2 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 scripts/ops/validate_codex_context_index.py configs/codex_task_context_index.json | Validate the canonical index. | Exit 0 with a complete bounded summary. |
| C3 | TARGET_ROOT | git diff --check | Check scoped patch whitespace. | Exit 0 with no findings. |

## Physical evidence

Bind source spec SHA, Task Card SHA, attempt identity, Target root, starting and final HEAD, complete diff, changed symbols, command outputs, verifier identities, and terminal state. Preserve fixture, canary, benchmark, and source evidence as distinct layers. Missing evidence fails closed.

## Independent review

A fresh reviewer must compare the approved specification, this card, complete scoped diff, RED/GREEN evidence, command outputs, benchmark or schema receipts, unrelated-state audit, and authority boundaries. Review cannot approve or integrate the Candidate.

## Exit conditions

- **PASS:** Index, validator, AGENTS, and task-launch skill converge with semantic tests and scoped Candidate evidence.
- **BLOCK:** Any authority gate is lost, a nonexistent command/path is admitted, or broad fallback remains silent.
- **Residual debt:** Additional task classes require later evidence-backed index extensions rather than speculative entries.
- **Next gate:** Independent Candidate acceptance, then documentation convergence may consume the accepted identities.
