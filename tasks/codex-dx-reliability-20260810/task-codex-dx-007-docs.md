# TASK-CODEX-DX-007-DOCS — Converge current developer documentation

- **Campaign:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source groups:** docs-convergence
- **Requirements:** REQ-007
- **Acceptance:** AC-007
- **Auto-chain:** `true`
- **Maximum claim:** static convergence
- **Depends on:** TASK-CODEX-DX-003-CONTEXT; TASK-CODEX-DX-004-BOOTSTRAP; TASK-CODEX-DX-005-TESTS; TASK-CODEX-DX-006-FIXTURES
- **Dependency unlock evidence:** accepted context index identity; accepted setup command identity; accepted test command identity; accepted smoke benchmark identity
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `wide-mechanical`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Update only current developer-facing documentation to reference the accepted context, setup, test, secret, and benchmark surfaces and remove or redirect obsolete commands.

## Observable outcome

current developer docs resolve only canonical commands and authority

## Non-goals

No historical archive rewrite, no docs/INDEX.md promotion, no product marketing claim, no new command identity, and no authority duplication.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-007 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-007 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |

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

- **Read:** AGENTS.md; README.md; CONTRIBUTING.md; docs/testing/test_runbook.md; openwiki/quickstart.md; configs/codex_task_context_index.json; scripts/ops/repo_doctor.py; scripts/ops/test_repo.sh; scripts/ci/run_swebench_subset.py
- **Edit:** README.md; CONTRIBUTING.md; docs/testing/test_runbook.md; openwiki/quickstart.md
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 3
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** CONTRIBUTING references obsolete commands; README provider-first preflight is over-broad; OpenWiki is derived and uses bare pytest.
- **Assumptions requiring verification:** Accepted upstream command identities remain stable through this documentation card.
- **Architecture risks:** Derived OpenWiki content could be mistaken for authority or duplicate executable contracts.
- **Evidence risks:** Link-only validation may miss contradictory prose or copied stale commands.
- **Missing owner decision:** none

## Mandatory source audit

Re-read root authority and all accepted upstream receipts. Search only current developer pages for obsolete command/path tokens and personal absolute paths; leave historical documents unchanged.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Confirm current pages contain stale `nexus:test --full-chain`, `FlashJudge 8.0`, provider-first core setup, bare pytest, or obsolete script paths; negative-control the command checker.

## Implementation constraints

Link to canonical executable surfaces, state authority ceilings, keep core/provider lanes distinct, avoid duplicating dynamic outputs, and preserve historical sources as historical.

## GREEN and regression gates

All current developer commands resolve, derived docs declare their ceiling, obsolete/personal paths are absent, and command/path audit passes.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 scripts/ops/validate_codex_context_index.py configs/codex_task_context_index.json | Validate canonical path and command mappings. | Exit 0. |
| C2 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_codex_task_context_index.py tests/ops/test_repo_test_commands.py tests/ops/test_repo_doctor.py | Run command/path/setup contract witnesses. | All selected tests pass. |
| C3 | TARGET_ROOT | git diff --check | Check scoped patch whitespace. | Exit 0 with no findings. |

## Physical evidence

Bind source spec SHA, Task Card SHA, attempt identity, Target root, starting and final HEAD, complete diff, changed symbols, command outputs, verifier identities, and terminal state. Preserve fixture, canary, benchmark, and source evidence as distinct layers. Missing evidence fails closed.

## Independent review

A fresh reviewer must compare the approved specification, this card, complete scoped diff, RED/GREEN evidence, command outputs, benchmark or schema receipts, unrelated-state audit, and authority boundaries. Review cannot approve or integrate the Candidate.

## Exit conditions

- **PASS:** Four current docs converge on accepted identities, static and focused tests pass, and scoped commit/Candidate evidence is formed.
- **BLOCK:** A current page retains contradictory commands, derived docs widen authority, or documentation invents a new command.
- **Residual debt:** Historical and superseded reports remain unchanged and are not current guidance.
- **Next gate:** Independent Candidate acceptance supplies the documentation receipt required by the after benchmark.
