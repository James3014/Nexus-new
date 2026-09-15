# TASK-514-001 — Contain legacy CapabilitySelector authority

- **Campaign:** `github-issue-514-capability-selector-containment-20260822`
- **Status:** `ACTIVE`
- **Source spec:** `SPEC-ISSUE-514-CAPABILITY-SELECTOR-CONTAINMENT`
- **Source spec SHA-256:** `edba2af79059a98be3cfb665da74c723199870505e5b84e33eba7a36b3abc8ea`
- **Source groups:** selector-containment
- **Requirements:** `REQ-001;REQ-002;REQ-003`
- **Acceptance:** `AC-001;AC-002;AC-003;AC-004`
- **Auto-chain:** `false`
- **Maximum claim:** `LEGACY_CAPABILITY_SELECTOR_AUTHORITY_CONTAINED_AT_SOURCE`
- **Depends on:** none
- **Dependency unlock evidence:** none
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

Make the affected legacy selector/router/learning CLI path consume or project `CapabilityPlanner` truth instead of independently selecting route/capabilities.

## Observable outcome

Legacy post-Planner controls cannot add/remove canonical selected capabilities or downgrade Planner-owned execution depth; learning CLI derives lite/full behavior from Planner truth.

## Non-goals

No new Router/Planner/registry; no provider/model/lifecycle changes; no receipt-coverage work; no #472 physical model-context work; no runtime-wide C9 claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| DEC-001 | owner authority | complete bounded repair |
| CON-001 | architecture authority | CapabilityPlanner sole selection authority |
| CON-002 | execution authority | governed mutation required |
| CUR-001;CUR-002;CUR-003 | defect evidence | current production-reachable second selector |

## Owner decisions

DEC-001.

## Source and start state

- **Workspace/root:** `/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-59512c5d`
- **Branch:** detached managed worktree based on exact main
- **Starting HEAD:** `d6b4bd77e8b559710ca103eeaa30f57b2e54fcdf`
- **Dirty baseline:** only coordinator-authored Task Card/spec files before implementation
- **Required initial verification:** confirm current source still contains independent `CapabilitySelector` lite/capability selection and caller chain
- **Freshness rule:** re-read HEAD/diff before commit and rebind if GitHub main moves before integration

## MCP execution profile

- **App/server and action snapshot:** Nexus Gateway observed but checkout stale at `aedc5f2607c0a6f7ecc7f7c0174854af3e6c38d3`; not used for mutation
- **Exact required actions:** not applicable; governed current-base DevSpace worktree
- **Confirmation-required actions:** none for bounded implementation; merge separately requires fresh standing grant
- **Idempotency and attempt rule:** one implementation attempt in this worktree; no blind replacement after ambiguous mutation
- **Reconnect reconciliation:** inspect exact workspace Git/diff before continuation
- **Transport blocker:** none for current-base DevSpace worktree

## Authority map

- **Selection authority:** `CapabilityPlanner`
- **Execution authority:** Issue #514 + this committed Task Card + Owner standing coordinator authority
- **Verification authority:** focused tests and independent acceptance
- **Receipt authority:** existing repository evidence contracts; unchanged
- **Approval/integration authority:** primary coordinator under fresh applicable standing grant only after independent acceptance

## Allowed scope

- **Read:** repository-wide bounded search as needed
- **Edit:** `nexus/core/capability_selector.py`; `nexus/core/router.py`; `scripts/engine/nexus_cli.py`; `tests/core/test_capability_selector_route_authority.py`; `tests/test_skills_router_builtin.py`; `tests/test_cli_learn_mode.py`
- **Create:** one narrowly named test file only if necessary
- **Delete:** none
- **Maximum touched production files:** 3
- **Maximum touched test files:** 4

## Unknown scan

- **Known facts:** verified alias map exists in `nexus/services/mainchain_route_freeze.py`; canonical and legacy namespaces differ.
- **Assumptions requiring verification:** existing canonical projection/executor helpers may allow reuse without new mapping.
- **Architecture risks:** recreating a second selector through a compatibility mapping.
- **Evidence risks:** old tests encode `NEXUS_SKIP_*` removal as desired behavior.
- **Missing owner decision:** none

## Mandatory source audit

Inspect `CapabilitySelector`, `SkillsRouter.route_candidates`, learn CLI callers, canonical `CapabilityPlanner`, canonical execution/projection helpers, semantic alias map, and affected tests before editing.

## Start-state classification

`DEFECT_REPRODUCED`

## RED or existing-guard proof

Current source independently calls lite oracle, assembles capabilities/phases, applies `NEXUS_SKIP_*`, and current test explicitly expects post-selection removal. This contradicts the canonical sole-authority invariant.

## Implementation constraints

Reuse existing canonical Planner/projection seams and verified semantic aliases. Do not invent string-similarity mappings. Fail closed when Planner truth cannot be projected safely. Preserve high-risk lite safety and existing constraint denial behavior without letting constraints become a second route selector.

## GREEN and regression gates

- Planner-selected canonical set/depth remains authoritative.
- Legacy compatibility cannot add/remove that truth.
- learning CLI uses Planner-derived lite/full state.
- force-lite/skip negative controls cannot override Planner safety/required selection.
- focused affected tests pass.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| V1 | repo root | `python -m pytest -q tests/core/test_capability_selector_route_authority.py tests/test_skills_router_builtin.py tests/test_cli_learn_mode.py` | focused behavior/regression | exit 0 |
| V2 | repo root | `python -m pytest -q tests/contracts/test_canonical_execution.py tests/services/test_light_route_authority_convergence.py` | canonical authority/safety affected regression | exit 0 |
| V3 | repo root | `git diff --check` | patch hygiene | exit 0 |

## Physical evidence

Bind final Candidate commit/tree/diff, complete changed paths, exact verifier outputs, and independent review to this Task Card/spec digest and starting base.

## Independent review

A fresh read-only reviewer must inspect exact Candidate diff for authority conservation, compatibility behavior, negative controls, out-of-scope changes, and test oracle strength. Implementer self-report is insufficient.

## Exit conditions

- **PASS:** all ACs physically evidenced on exact Candidate; scoped commit exists; independent acceptance passes.
- **BLOCK:** canonical projection cannot be made without inventing authority/mapping, required tests are invalid, or scope must widen.
- **Residual debt:** runtime C9 and receipt coverage remain separate.
- **Next gate:** independent Candidate acceptance, then protected merge under fresh standing-grant/CAS checks.
