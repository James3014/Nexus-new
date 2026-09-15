# TASK-002 — Implement persistent ChatGPT Web worker and task-conversation runtime

- **Campaign:** `CAMPAIGN-DEV-MCP-WEB-BATCH-AUTONOMY-001`
- **Status:** `BLOCKED`
- **Source spec:** `SPEC-DEV-MCP-WEB-BATCH-AUTONOMY-001`
- **Source spec SHA-256:** `fc57f20b2133ed98c8f0c5eabcd6bbe5567aa8a3f97aef70b2eca1ba42bf9d22`
- **Source groups:** TG-2 Web worker runtime and conversations
- **Requirements:** REQ-004; REQ-005; REQ-015
- **Acceptance:** AC-004; AC-005; AC-015
- **Auto-chain:** `false`
- **Maximum claim:** Live worker/conversation behavior for tested runtime only.
- **Depends on:** TASK-003
- **Dependency unlock evidence:** Accepted typed batch-grant primitives available to bind worker/task authority, with execution-time DevSpace source/package rebinding and macOS browser/ChatGPT Web control-seam proof before mutation.
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `DIRECT_TYPED_ACTIONS`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Implement persistent ChatGPT Web worker and task-conversation runtime without broadening the approved source specification.

## Observable outcome

A persistent worker identity can host separate task conversations that survive supported reconnect/restart and remain retained after completion.

## Non-goals

- No approval, integration, protected push, release, deployment, production/public claim, or unrelated cleanup.
- Do not widen the source specification, sibling task scope, or current provider/tool authority.
- Do not absorb unrelated dirty state.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-004 | Binding requirement | Preserve exact source behavior and failure semantics. |
| REQ-005 | Binding requirement | Preserve exact source behavior and failure semantics. |
| REQ-015 | Binding requirement | Preserve exact source behavior and failure semantics. |
| AC-004 | Acceptance witness | Preserve falsifiable physical verification seam and negative control. |
| AC-005 | Acceptance witness | Preserve falsifiable physical verification seam and negative control. |
| AC-015 | Acceptance witness | Preserve falsifiable physical verification seam and negative control. |

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
- **Exact required actions:** open_workspace;agent_start;agent_status;agent_continue;agent_reconcile;workspace_verify;git_commit
- **Confirmation-required actions:** agent_start;git_commit
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

- **Read:** AGENTS.md; src/workspaces.ts; src/workspace-conversation.test.ts; src/local-agent-sessions.ts; src/db/schema.ts; src/db/migrations.ts; src/server.ts
- **Edit:** none
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 0
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** Existing workspace conversation bindings persist checkout context; provider sessions already expose durable conversation IDs for Agy. Agy read-only smoke succeeded on 2026-08-23 with agy 1.1.19 and no changed paths.
- **Assumptions requiring verification:** Before implementation, rebind which DevSpace source checkout/packages the live MCP and durable-agent runtime, then select a provider-neutral ChatGPT Web adapter seam; do not absorb the current unrelated dirty Agy changes.
- **Architecture risks:** Browser DOM/session drift and authenticated profile handling are the main live-runtime risks.
- **Evidence risks:** Reports/status alone cannot prove the linked acceptance criteria; preserve exact revision and negative-control evidence.
- **Missing owner decision:** none

## Mandatory source audit

Re-read the listed allowed Read paths, root AGENTS.md, relevant caller/consumer tests, current source Spec REQ/AC, and predecessor receipts. Search for existing equivalent authority/runtime/state-machine seams before creating a new mechanism. Preserve unrelated dirty state and current protected integration boundaries.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

This is a proof-only card. It does not claim a defect or authorize mutation; its job is to bind current seams and falsify unsafe assumptions.

## Implementation constraints

Read-only only. Produce evidence that can freeze exact downstream mutation paths; do not repair the dirty Agy branch or create files.

## GREEN and regression gates

Satisfy every linked AC at the highest listed verification seam; run all command-manifest gates; independently inspect changed/deleted paths and preserve negative controls. For blocked cards, GREEN cannot be claimed until a superseding exact-scope card exists.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | `npx tsx src/workspace-conversation.test.ts` | Conversation persistence regression | Pass. |
| C2 | TARGET_ROOT | `npx tsx src/local-agent-sessions.test.ts` | Durable session regression | Pass. |
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