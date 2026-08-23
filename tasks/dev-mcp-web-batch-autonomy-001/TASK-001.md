# TASK-001 — Define the Nexus batch-autonomy authority contract

- **Campaign:** `CAMPAIGN-DEV-MCP-WEB-BATCH-AUTONOMY-001`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-DEV-MCP-WEB-BATCH-AUTONOMY-001`
- **Source spec SHA-256:** `fc57f20b2133ed98c8f0c5eabcd6bbe5567aa8a3f97aef70b2eca1ba42bf9d22`
- **Source groups:** TG-1 Authority and grant contracts
- **Requirements:** REQ-001; REQ-020; REQ-022
- **Acceptance:** AC-001; AC-020; AC-022
- **Auto-chain:** `false`
- **Maximum claim:** Policy/contract correctness only; no live worker claim.
- **Depends on:** none
- **Dependency unlock evidence:** none
- **Task type:** `CONTRACT`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Define the Nexus batch-autonomy authority contract without broadening the approved source specification.

## Observable outcome

Current Nexus authority explicitly preserves DIRECT_DELEGATED while defining a separate external batch-autonomy lane and its outside-Nexus routing boundary.

## Non-goals

- No approval, integration, protected push, release, deployment, production/public claim, or unrelated cleanup.
- Do not widen the source specification, sibling task scope, or current provider/tool authority.
- Do not absorb unrelated dirty state.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-001 | Binding requirement | Preserve exact source behavior and failure semantics. |
| REQ-020 | Binding requirement | Preserve exact source behavior and failure semantics. |
| REQ-022 | Binding requirement | Preserve exact source behavior and failure semantics. |
| AC-001 | Acceptance witness | Preserve falsifiable physical verification seam and negative control. |
| AC-020 | Acceptance witness | Preserve falsifiable physical verification seam and negative control. |
| AC-022 | Acceptance witness | Preserve falsifiable physical verification seam and negative control. |

## Owner decisions

Source Spec owner decisions are already settled; no new Owner decision in this card.

## Source and start state

- **Workspace/root:** /Users/jameschen/Workspace/Nexus-new
- **Branch:** main@GitHub
- **Starting HEAD:** 67521fe91e990f4e140642984c743dd50a408e84
- **Dirty baseline:** Canonical GitHub main is clean; ordinary local checkout is dirty/behind and must not be used as mutation baseline.
- **Required initial verification:** Re-read root, branch/identity, HEAD, dirty state, and applicable instruction files before the task starts.
- **Freshness rule:** Re-read after any predecessor completion, repository movement, reconnect, tool/profile change, or material delay before mutation/proof.

## MCP execution profile

- **App/server and action snapshot:** Nexus gateway; exact server/tool manifest and permission hashes must be refreshed before execution.
- **Exact required actions:** nexus_task_run;nexus_task_status;nexus_task_reconcile;nexus_task_finish
- **Confirmation-required actions:** nexus_task_run;nexus_task_finish
- **Idempotency and attempt rule:** Bind task_id, attempt identity, expected HEAD, source Task Card hash, and request hash; never replay uncertain mutation before reconcile.
- **Reconnect reconciliation:** Re-read gateway identity and task status, then nexus_task_reconcile before retry/resume.
- **Transport blocker:** none

## Authority map

- **Selection authority:** CapabilityPlanner/current Nexus route authority
- **Execution authority:** Nexus lifecycle executor bound by the active Task Card
- **Verification authority:** Independent coordinator/reviewer using the listed physical seams
- **Receipt authority:** Nexus lifecycle receipt bound to Task Card/Candidate
- **Approval/integration authority:** Owner/coordinator authority remains separate; worker cannot approve/integrate/merge.

## Allowed scope

- **Read:** AGENTS.md; docs/agents/TASK_EXECUTION_CONTRACT.md; docs/agents/WORKFORCE_EXECUTION_OVERLAY.md; tests/ops/test_bootstrap_authority_files.py; tests/ops/test_bootstrap_context_budget.py
- **Edit:** AGENTS.md; docs/agents/TASK_EXECUTION_CONTRACT.md; docs/agents/WORKFORCE_EXECUTION_OVERLAY.md; tests/ops/test_bootstrap_authority_files.py; tests/ops/test_bootstrap_context_budget.py
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 3
- **Maximum touched test files:** 2

## Unknown scan

- **Known facts:** GitHub main was rebound at 67521fe9. Local checkout baseline test currently shows AGENTS.md 12111 bytes > 12000 budget; re-run at exact execution baseline before attributing.
- **Assumptions requiring verification:** The new lane can be expressed additively in existing authority contracts without changing CapabilityPlanner.
- **Architecture risks:** Authority prose can silently broaden existing lanes; root AGENTS.md has a tight context budget.
- **Evidence risks:** Reports/status alone cannot prove the linked acceptance criteria; preserve exact revision and negative-control evidence.
- **Missing owner decision:** none

## Mandatory source audit

Re-read the listed allowed Read paths, root AGENTS.md, relevant caller/consumer tests, current source Spec REQ/AC, and predecessor receipts. Search for existing equivalent authority/runtime/state-machine seams before creating a new mechanism. Preserve unrelated dirty state and current protected integration boundaries.

## Start-state classification

`PREEXISTING_BASELINE_FAILURE`

## RED or existing-guard proof

At current local checkout, focused authority tests show a pre-existing context-budget failure; exact GitHub-main execution baseline must be re-run before assigning causality. The card must preserve DIRECT_DELEGATED negative controls and the 12 KB root-context guard.

## Implementation constraints

Keep root AGENTS.md minimal; place detailed batch-lane semantics in the narrowest existing contract while preserving CapabilityPlanner and DIRECT_DELEGATED invariants.

## GREEN and regression gates

Satisfy every linked AC at the highest listed verification seam; run all command-manifest gates; independently inspect changed/deleted paths and preserve negative controls. For blocked cards, GREEN cannot be claimed until a superseding exact-scope card exists.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | `python3 -m pytest -q tests/ops/test_bootstrap_authority_files.py tests/ops/test_bootstrap_context_budget.py` | Authority and context-budget regression gate | All focused tests pass at candidate revision; record any exact-main baseline failure separately. |
| C2 | TARGET_ROOT | `git diff --check` | Whitespace/conflict marker guard | Exit 0. |

## Physical evidence

Bind task/attempt identity, source spec SHA, starting and final revision, exact changed/deleted paths, candidate commit/tree when applicable, command identities/results, worker/provider session identity when applicable, and independent review evidence. Separate fixture/simulation/canary/live-runtime evidence and never infer later lifecycle states from earlier ones.

## Independent review

Use a fresh reviewer/coordinator distinct from the implementer. Review source Spec/REQ/AC lineage, exact diff, negative controls, command evidence, authority boundaries, unexpected paths/deletions, and claim ceiling. Worker PASS is not acceptance.

## Exit conditions

- **PASS:** All linked acceptance criteria are physically witnessed, scope/authority checks pass, required commands pass, and candidate/proof evidence is revision-bound.
- **BLOCK:** Any predecessor/transport/authority mismatch, unresolved exact scope, stale identity, scope violation, missing negative control, verifier failure, or evidence ambiguity blocks the card without auto-chaining.
- **Residual debt:** Record any distinct bounded survivor separately; do not silently widen this card.
- **Next gate:** nexus-model-task-compiler only after this card is ACTIVE, exact-scope, fresh, and execution-authorized; otherwise supersede/recompile first.