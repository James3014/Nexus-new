# TASK-008 — Implement independent acceptance and GitHub/local completion gates

- **Campaign:** `CAMPAIGN-DEV-MCP-WEB-BATCH-AUTONOMY-001`
- **Status:** `BLOCKED`
- **Source spec:** `SPEC-DEV-MCP-WEB-BATCH-AUTONOMY-001`
- **Source spec SHA-256:** `fc57f20b2133ed98c8f0c5eabcd6bbe5567aa8a3f97aef70b2eca1ba42bf9d22`
- **Source groups:** TG-7 Verification and completion
- **Requirements:** REQ-016; REQ-017; REQ-018
- **Acceptance:** AC-016; AC-017; AC-018
- **Auto-chain:** `false`
- **Maximum claim:** Completion/acceptance claim only; not production or release.
- **Depends on:** TASK-003; TASK-004; TASK-005; TASK-007
- **Dependency unlock evidence:** Kickoff grant and optional coordinator-only merge semantics accepted.; Controller task/result states accepted.; Candidate/worktree physical evidence bridge accepted.; Uncertain failure recovery produces reconciled attempt/effect identity.
- **Task type:** `INTEGRATION_VERIFY`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `DIRECT_TYPED_ACTIONS`
- **Minimum MCP profile:** `MUTATE_BOUNDED`
- **Commit required:** `false`
- **Candidate required:** `false`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Implement independent acceptance and GitHub/local completion gates without broadening the approved source specification.

## Observable outcome

The Main Controller independently accepts physical results and reports GitHub or local Completion only when terminal-state and verifier evidence satisfy the source specification.

## Non-goals

- No approval, integration, protected push, release, deployment, production/public claim, or unrelated cleanup.
- Do not widen the source specification, sibling task scope, or current provider/tool authority.
- Do not absorb unrelated dirty state.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-016 | Binding requirement | Preserve exact source behavior and failure semantics. |
| REQ-017 | Binding requirement | Preserve exact source behavior and failure semantics. |
| REQ-018 | Binding requirement | Preserve exact source behavior and failure semantics. |
| AC-016 | Acceptance witness | Preserve falsifiable physical verification seam and negative control. |
| AC-017 | Acceptance witness | Preserve falsifiable physical verification seam and negative control. |
| AC-018 | Acceptance witness | Preserve falsifiable physical verification seam and negative control. |

## Owner decisions

Source Spec owner decisions are already settled; no new Owner decision in this card.

## Source and start state

- **Workspace/root:** REVERIFY_AFTER_DEPENDENCY
- **Branch:** REVERIFY_AFTER_DEPENDENCY
- **Starting HEAD:** REVERIFY_AFTER_DEPENDENCY
- **Dirty baseline:** REVERIFY_AFTER_DEPENDENCY
- **Required initial verification:** Re-read all start-state fields after predecessor evidence and before mutation.
- **Freshness rule:** Re-read after any predecessor completion, repository movement, reconnect, tool/profile change, or material delay before mutation/proof.

## MCP execution profile

- **App/server and action snapshot:** DevSpace; exact live profile/action inventory must be refreshed before dispatch.
- **Exact required actions:** open_workspace;agent_start;agent_status;agent_reconcile;workspace_verify
- **Confirmation-required actions:** agent_start
- **Idempotency and attempt rule:** Bind workspaceId, exact agentId, expected HEAD, execution contract, and candidate path set; after uncertain return reconcile the same agent before continuation/replacement.
- **Reconnect reconciliation:** Use agent_status and agent_reconcile on the same agentId; inspect physical Git/files before any semantic continuation.
- **Transport blocker:** none

## Authority map

- **Selection authority:** Main Controller under approved campaign contract
- **Execution authority:** Bounded Agy/other worker selected by the later model compiler; no authority from this card alone
- **Verification authority:** Independent coordinator/reviewer using the listed physical seams
- **Receipt authority:** DevSpace agent/candidate evidence plus independent verifier record
- **Approval/integration authority:** Owner/coordinator authority remains separate; worker cannot approve/integrate/merge.

## Allowed scope

- **Read:** AGENTS.md; src/git-candidate.ts; src/workspace-reconciliation.ts; src/local-agent-sessions.ts; src/server.ts
- **Edit:** none
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 0
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** Existing candidate commit/push guards and agent reconciliation can supply physical evidence; integration authority remains separate.
- **Assumptions requiring verification:** GitHub merge execution remains outside this verification card and must use current protected merge authority after acceptance.
- **Architecture risks:** A green worker report or closed-but-unmerged PR must never satisfy completion.
- **Evidence risks:** Reports/status alone cannot prove the linked acceptance criteria; preserve exact revision and negative-control evidence.
- **Missing owner decision:** none

## Mandatory source audit

Re-read the listed allowed Read paths, root AGENTS.md, relevant caller/consumer tests, current source Spec REQ/AC, and predecessor receipts. Search for existing equivalent authority/runtime/state-machine seams before creating a new mechanism. Preserve unrelated dirty state and current protected integration boundaries.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Before implementation, demonstrate the predecessor-bound existing guard/absence at the public seam and record why current behavior cannot satisfy the linked acceptance criteria. A fixture/import failure is not product RED.

## Implementation constraints

Implement only after predecessors freeze exact scope. This blocked card intentionally carries no mutation paths; execution requires an explicit superseding card with revision-bound exact Edit/Create/Delete paths. Preserve adapter boundaries, typed actions, least privilege, and no self-approval.

## GREEN and regression gates

Satisfy every linked AC at the highest listed verification seam; run all command-manifest gates; independently inspect changed/deleted paths and preserve negative controls. For blocked cards, GREEN cannot be claimed until a superseding exact-scope card exists.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | `npx tsx src/git-candidate.test.ts` | Candidate evidence and protected-ref regression | Pass. |
| C2 | TARGET_ROOT | `npx tsx src/server.test.ts` | Public completion/tool surface regression | Pass. |
| C3 | TARGET_ROOT | `npm run typecheck` | Type gate | Pass. |

## Physical evidence

Bind task/attempt identity, source spec SHA, starting and final revision, exact changed/deleted paths, candidate commit/tree when applicable, command identities/results, worker/provider session identity when applicable, and independent review evidence. Separate fixture/simulation/canary/live-runtime evidence and never infer later lifecycle states from earlier ones.

## Independent review

Use a fresh reviewer/coordinator distinct from the implementer. Review source Spec/REQ/AC lineage, exact diff, negative controls, command evidence, authority boundaries, unexpected paths/deletions, and claim ceiling. Worker PASS is not acceptance.

## Exit conditions

- **PASS:** All linked acceptance criteria are physically witnessed, scope/authority checks pass, required commands pass, and candidate/proof evidence is revision-bound.
- **BLOCK:** Any predecessor/transport/authority mismatch, unresolved exact scope, stale identity, scope violation, missing negative control, verifier failure, or evidence ambiguity blocks the card without auto-chaining.
- **Residual debt:** Record any distinct bounded survivor separately; do not silently widen this card.
- **Next gate:** nexus-model-task-compiler only after this card is ACTIVE, exact-scope, fresh, and execution-authorized; otherwise supersede/recompile first.