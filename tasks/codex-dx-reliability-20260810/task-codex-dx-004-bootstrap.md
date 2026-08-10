# TASK-CODEX-DX-004-BOOTSTRAP — Make core setup portable and secrets-free

- **Campaign:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source groups:** core-bootstrap
- **Requirements:** REQ-003; REQ-004
- **Acceptance:** AC-003; AC-004
- **Auto-chain:** `true`
- **Maximum claim:** core setup canary pass
- **Depends on:** TASK-CODEX-DX-001-BEFORE
- **Dependency unlock evidence:** accepted immutable before-arm setup receipt
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

Create a portable core repository doctor and tested Python pin, narrow provider preflight requirements, and define explicit secret classification without reading live secret files.

## Observable outcome

clean-cache secrets-free setup canary

## Non-goals

No provider onboarding, no live `.env` edits, no API calls, no model download, no route change, and no production-ready claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-003 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| REQ-004 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-003 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-004 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |

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

- **Read:** pyproject.toml; uv.lock; scripts/ops/_nexus_preflight.sh; .env.template; tests/test_uv_cache_isolation.py; tests/ops/test_nexus_benchmark_preflight.py; tests/pilot_cli/test_secret_handling.py; scripts/engine/nexus_cli.py
- **Edit:** scripts/ops/_nexus_preflight.sh; .env.template
- **Create:** .python-version; scripts/ops/repo_doctor.py; tests/ops/test_repo_doctor.py
- **Delete:** none
- **Maximum touched production files:** 4
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** Core README preflight currently requires Node and Gemini, appends personal paths, and reports production-ready; local Python is 3.14 while CI primarily uses 3.12.
- **Assumptions requiring verification:** Python 3.12 is the common tested interpreter and provider tools can remain optional for core work.
- **Architecture risks:** Narrowing preflight must not weaken provider-specific commands or lifecycle readiness checks.
- **Evidence risks:** A doctor may pass by finding globally installed tools or reading a warm home cache.
- **Missing owner decision:** none

## Mandatory source audit

Inspect pyproject/lock, preflight, uv cache isolation, provider preflight, CLI help seam, and secret-handling tests. Never read the live `.env` file.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Run with an unwritable home cache, scrubbed provider variables, missing Gemini/Node, and unsupported Python; record current ambiguous or over-broad failure behavior.

## Implementation constraints

Use PATH discovery, temporary/project-local uv cache guidance, structured JSON and human output, no personal absolute paths, no secret values, and explicit core versus provider states.

## GREEN and regression gates

Core doctor passes in a clean cache without provider tools or secrets; unsupported Python/cache/core dependencies fail precisely; provider requirements are explicit and redacted.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_repo_doctor.py tests/test_uv_cache_isolation.py tests/ops/test_nexus_benchmark_preflight.py tests/pilot_cli/test_secret_handling.py | Validate setup, cache, provider, and secret boundaries. | All selected tests pass. |
| C2 | TARGET_ROOT | UV_CACHE_DIR=/tmp/nexus-codex-dx-uv-cache PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python scripts/ops/repo_doctor.py --format json | Run clean-cache core doctor canary. | Exit 0 with core ready and provider state explicit. |
| C3 | TARGET_ROOT | bash -n scripts/ops/_nexus_preflight.sh | Validate shell syntax. | Exit 0. |
| C4 | TARGET_ROOT | git diff --check | Check scoped patch whitespace. | Exit 0 with no findings. |

## Physical evidence

Bind source spec SHA, Task Card SHA, attempt identity, Target root, starting and final HEAD, complete diff, changed symbols, command outputs, verifier identities, and terminal state. Preserve fixture, canary, benchmark, and source evidence as distinct layers. Missing evidence fails closed.

## Independent review

A fresh reviewer must compare the approved specification, this card, complete scoped diff, RED/GREEN evidence, command outputs, benchmark or schema receipts, unrelated-state audit, and authority boundaries. Review cannot approve or integrate the Candidate.

## Exit conditions

- **PASS:** Portable doctor, Python pin, preflight split, secret template, tests, clean-cache canary, scoped commit, and Candidate evidence pass.
- **BLOCK:** Core still requires provider credentials/tools, personal paths remain, secrets are exposed, or supported interpreter/lock semantics cannot be reconciled.
- **Residual debt:** Optional provider installation remains separately documented and out of core setup.
- **Next gate:** Independent Candidate acceptance unlocks the canonical test contract.
