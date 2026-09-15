# Dev MCP Persistent ChatGPT Web Batch Autonomy

- **Spec ID:** `SPEC-DEV-MCP-WEB-BATCH-AUTONOMY-001`
- **Status:** `READY_FOR_TASK_CARDS`
- **Basis snapshot:** GitHub `James3014/Nexus-new` main `67521fe91e990f4e140642984c743dd50a408e84`; Nexus gateway instance `d76d773594524a2c93f02ddf98bc920c` at runtime worktree HEAD `aedc5f2607c0a6f7ecc7f7c0174854af3e6c38d3`; live Dev MCP inventory observed 2026-08-23
- **Supersedes:** `none`
- **Claim ceiling:** Owner-confirmed implementation specification; no implementation, runtime readiness, merge, release, deployment, or production claim
- **Source interview:** `nexus-dev-mcp-ultra-20260823`
- **Source interview SHA-256:** `97e7d5e78f31d9a129427d4a5018e36874a4038f18b39315c716cb455e1cd731`

## 1. Problem statement

The current Dev MCP can operate workspaces, durable coding agents, verification, commits, and non-default-branch pushes, but it does not expose a native persistent ChatGPT Web worker pool or a one-kickoff authority model for parallel autonomous work. The current Nexus `DIRECT_DELEGATED` lane is intentionally narrower: one bounded external worker, independent coordinator verification, and no auto-chain. The Owner wants a separate low-friction mode in which the Main Controller can run multiple independent ChatGPT Web workers concurrently, let them finish routine engineering autonomously, recursively delegate bounded subwork, recover failures, independently verify results, and complete GitHub or local work without repeated Owner interruptions.

## 2. Desired outcome

After one explicit kickoff confirmation for a bounded Goal, the Main Controller can safely run the entire authorized batch to completion: dynamically derive child tasks, exploit safe parallelism, dispatch persistent ChatGPT Web workers, isolate mutations, allow least-privilege nested delegation, recover uncertain failures, independently verify results, and perform covered GitHub merge/close when the kickoff grant includes that authority. The Owner is contacted only for Completion or a True Blocker.

## 3. Basis, coverage, and freshness

The binding design basis is Nexus interview `nexus-dev-mcp-ultra-20260823` with exact byte SHA-256 `97e7d5e78f31d9a129427d4a5018e36874a4038f18b39315c716cb455e1cd731` and canonical ledger SHA-256 `8193d51c6714b6f0d0c4a8b03cb3a0890f0b8fa6a4c47ae5dd94e7424fe9b7a4`. Its upstream product/system interview is `/mnt/data/dev-mcp-ultra-interview-ledger.json`. Both are owner-confirmed; the Nexus ledger is `READY_FOR_SPEC`.

Current repository contracts were re-read from GitHub main `67521fe91e990f4e140642984c743dd50a408e84`. The connected Nexus gateway was separately observed at runtime worktree HEAD `aedc5f2607c0a6f7ecc7f7c0174854af3e6c38d3`; that runtime snapshot is not treated as the latest repository source revision. The ordinary local checkout `/Users/jameschen/Workspace/Nexus-new` was observed dirty and far behind `origin/main`, so it is not a safe implementation baseline. Task-card compilation MUST rebind the exact repository, transport, Dev MCP manifest, and policy state before mutation.

The live Dev MCP action inventory is dynamic. This specification binds behavior to the capability envelope observed on 2026-08-23 and requires re-discovery rather than assuming the same action list forever. No browser/ChatGPT Web worker implementation is claimed to exist today.

## 4. Source and decision ledger

| ID | Class | Statement | Authority/location | Freshness/snapshot | Status | Limitation |
|---|---|---|---|---|---|---|
| DEC-001 | DEC | Preserve DIRECT_DELEGATED unchanged and add a separate lightweight batch/swarm authority lane for one-kickoff autonomous parallel orchestration. | nexus interview DEC-001 | 2026-08-23 / READY_FOR_SPEC | BINDING | Owner-confirmed Nexus governance mapping. |
| DEC-002 | DEC | Keep the new batch/swarm lane outside Nexus runtime. DevSpace/ChatGPT Web is the routine execution control plane; CapabilityPlanner and Nexus Workforce Admission do not participate solely because of external batch orchestration. | nexus interview DEC-002 | 2026-08-23 / READY_FOR_SPEC | BINDING | Owner-confirmed Nexus governance mapping. |
| DEC-003 | DEC | Bound the batch-autonomy grant by one Owner-confirmed Goal plus an explicit policy/authority envelope; the main controller may derive and create necessary child tasks dynamically when they remain causally within that Goal. | nexus interview DEC-003 | 2026-08-23 / READY_FOR_SPEC | BINDING | Owner-confirmed Nexus governance mapping. |
| DEC-004 | DEC | The batch-autonomy grant may explicitly include GITHUB_MERGE at kickoff for the exact Goal/repository/coordinator scope. Only the main controller may exercise it after independent acceptance and fresh merge-gate verification; workers and descendant agents never inherit merge authority. | nexus interview DEC-004 | 2026-08-23 / READY_FOR_SPEC | BINDING | Owner-confirmed Nexus governance mapping. |
| DEC-005 | DEC | Recursive subagent delegation uses a newly bounded child authorization for each subtask. Authority may only narrow across descendants; it may never expand. Coordinator-only merge/integration authority, final independent acceptance, and Owner-only decisions are never delegated. Full descendant lineage and results must return to the main controller. | nexus interview DEC-005 | 2026-08-23 / READY_FOR_SPEC | BINDING | Owner-confirmed Nexus governance mapping. |
| DEC-006 | DEC | Primary target is concurrent multi-work orchestration plus ChatGPT Web workers. | upstream interview DEC-001 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-007 | DEC | ChatGPT Web workers are independently identifiable persistent workers. | upstream interview DEC-002 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-008 | DEC | Main controller may dispatch each safely parallelizable task to a separate GPT Web worker concurrently. | upstream interview DEC-003 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-009 | DEC | Workers execute end-to-end autonomously after assignment and normally report only after completion. | upstream interview DEC-004 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-010 | DEC | After one kickoff confirmation, the controller autonomously decomposes, parallelizes, dispatches, tracks, retries, reassigns, and verifies until completion or a true owner-only boundary. | upstream interview DEC-005 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-011 | DEC | GitHub completion requires Issue closed or PR merged and therefore closed; an unmerged closed PR is not success. | upstream interview DEC-006 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-012 | DEC | GPT Web worker may implement through PR-ready state; main controller independently verifies and performs merge/close under applicable authority. | upstream interview DEC-007 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-013 | DEC | Use persistent worker identity plus separate recoverable conversation per Issue/task. | upstream interview DEC-008 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-014 | DEC | The system supports both GitHub-backed and local tasks; GitHub is a task source, not the task abstraction itself. | upstream interview DEC-009 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-015 | DEC | Every mutating parallel task uses its own worktree; read-only research/review may share a checkout. | upstream interview DEC-010 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-016 | DEC | ChatGPT Web workers should be able to perform engineering work up to the current Dev MCP capability envelope, subject to the same applicable authority constraints. | upstream interview DEC-011 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-017 | DEC | Always-on execution while the owner Mac is powered off is not required for this specification. | upstream interview DEC-012 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-018 | DEC | GPT Web workers may delegate bounded subwork to other agents, but the complete downstream delegation/action/result chain must be reported to the main controller. | upstream interview DEC-013 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-019 | DEC | Pause only the affected task; all independent tasks continue; ask the owner only the minimal blocking question. | upstream interview DEC-014 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-020 | DEC | The main controller elastically scales the number of ChatGPT Web workers to safe parallelism, bounded by a configurable maximum; excess work queues. | upstream interview DEC-015 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-021 | DEC | On worker loss, controller first restores the original worker/task conversation; if impossible, it reconciles physical state before transferring work to a replacement. Other workers continue. | upstream interview DEC-016 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-022 | DEC | Normal execution stays quiet; controller reports details when work completes or when a true blocker requires owner input. | upstream interview DEC-017 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-023 | DEC | Completed task conversations are retained long-term by default until manual cleanup or a future explicit cleanup policy. | upstream interview DEC-018 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-024 | DEC | Owner-only boundaries are limited to intent/scope changes, security/governance weakening, new irreversible external effects, release/production/public commitments, and materially unknowable authority/truth states. Routine engineering work is autonomous. | upstream interview DEC-019 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| DEC-025 | DEC | Local tasks do not need to be promoted to GitHub. Completion requires the requested result to physically exist, applicable tests/verifiers to pass, and the main controller to independently inspect the result; mutating Git work should leave a scoped commit or other explicitly requested local deliverable. | upstream interview DEC-020 | 2026-08-23 / READY_FOR_ADAPTER | BINDING | Owner-confirmed product/system decision. |
| CUR-001 | CUR | Current Dev MCP exposes 15 typed actions covering workspace/worktree open, file read/write/edit, bounded shell inspection/verification, durable agent lifecycle, reconciliation, scoped commit, and non-default-branch push; no native ChatGPT Web worker action is present in the observed inventory. | connected Dev MCP tool inventory | observed 2026-08-23 | EVIDENCE | Tool surface is dynamic and must be re-read before implementation. |
| CUR-002 | CUR | Current Nexus gateway reports server nexus-mcp-gateway, instance d76d773594524a2c93f02ddf98bc920c, CapabilityPlanner as route authority, 28 tools, no repository or runtime-source drift, and canonical runtime worktree HEAD aedc5f2607c0a6f7ecc7f7c0174854af3e6c38d3. | connected Nexus gateway status | observed 2026-08-23 | EVIDENCE | Runtime worktree is a transport/runtime snapshot, not the latest GitHub main source revision. |
| CUR-003 | CUR | GitHub collaboration main is 67521fe91e990f4e140642984c743dd50a408e84 at the specification basis snapshot. | GitHub James3014/Nexus-new main | observed 2026-08-23 | EVIDENCE | Must be rebound before implementation because main can move. |
| CON-001 | CON | Current root AGENTS.md defines DIRECT_DELEGATED as exactly one bounded external worker with independent coordinator verification and AUTO_CHAIN=false; ordinary retry/rebind/evidence is coordinator-autonomous while real scope, security, irreversible-effect, release, or production boundaries require Owner action. | James3014/Nexus-new AGENTS.md at 67521fe91e990f4e140642984c743dd50a408e84 | blob e4d89c392378f9084393fc45f3461fe75b960e0e | BINDING | Canonical repository authority for current execution lanes. |
| CON-002 | CON | Current Task Execution Contract preserves the one-worker DIRECT_DELEGATED boundary, requires reconciliation before retry after timeout/disconnect, prohibits delegated self-approval/integration, and treats program-level AUTO_CHAIN as outside DIRECT_DELEGATED. | docs/agents/TASK_EXECUTION_CONTRACT.md at 67521fe91e990f4e140642984c743dd50a408e84 | blob a05bbbf36072386c9a56012148fab6feace994f2 | BINDING | Canonical execution contract baseline. |
| CON-003 | CON | Current Workforce Execution Overlay states that Nexus runtime execution requires Workforce Admission, while Owner-authorized DIRECT_DELEGATED work through DevSpace does not; external output remains non-self-approving candidate evidence. | docs/agents/WORKFORCE_EXECUTION_OVERLAY.md at 67521fe91e990f4e140642984c743dd50a408e84 | blob d5b84797cda40ae91df821ea37f3f5e2cb6f2a5f | BINDING | Canonical workforce boundary baseline. |
| REJ-001 | REJ | Do not broaden or redefine existing DIRECT_DELEGATED to carry batch autonomy. | nexus interview DEC-001 | 2026-08-23 | REJECTED | Owner chose a separate lightweight lane. |
| REJ-002 | REJ | Do not force routine DevSpace or ChatGPT Web batch orchestration through Nexus runtime routing or Workforce Admission solely because it is multi-worker. | nexus interview DEC-002 | 2026-08-23 | REJECTED | Owner chose external control-plane execution. |
| REJ-003 | REJ | Do not require a fixed enumerated child-task list at kickoff. | nexus interview DEC-003 | 2026-08-23 | REJECTED | Owner chose Goal-bounded dynamic child tasks. |
| REJ-004 | REJ | Do not require a second merge grant or per-PR Owner approval when GITHUB_MERGE was explicitly included in the kickoff grant and fresh merge gates pass. | nexus interview DEC-004 | 2026-08-23 | REJECTED | Owner chose optional kickoff merge authority for the main controller only. |
| REJ-005 | REJ | Do not let descendant workers inherit the full parent or batch grant. | nexus interview DEC-005 | 2026-08-23 | REJECTED | Owner chose monotonically narrowing descendant authority. |

## 5. Current verified state

- `CUR-001`: the observed Dev MCP has typed workspace/worktree, file, verification, durable-agent, reconciliation, commit, and non-default-branch push actions, but no native ChatGPT Web worker action.
- `CUR-002`: the connected Nexus runtime is healthy at the observed snapshot, has `CapabilityPlanner` as route authority, and reports no repository/runtime-source drift; this is runtime evidence only.
- `CUR-003`: GitHub collaboration main is `67521fe91e990f4e140642984c743dd50a408e84` at this spec snapshot.
- `CON-001` and `CON-002`: current `DIRECT_DELEGATED` is intentionally one-worker/no-auto-chain and already requires independent coordinator verification plus reconcile-before-retry behavior.
- `CON-003`: external DevSpace delegation is outside Nexus Workforce Admission; Nexus-runtime work remains under Nexus route/admission authority.

## 6. Owner decisions

The binding Owner decisions are `DEC-001` through `DEC-025`. In particular: preserve `DIRECT_DELEGATED` and add a separate batch-autonomy lane; keep routine batch execution in DevSpace/ChatGPT Web outside Nexus runtime; bind one kickoff grant to a Goal with dynamic child tasks; allow optional coordinator-only `GITHUB_MERGE`; make descendant authority monotonically narrower; use persistent worker identities with task-scoped recoverable conversations; isolate mutating tasks by worktree; allow recursive subagents with complete lineage; keep Owner interruption limited to True Blockers; and define separate GitHub and local completion evidence.

Explicitly rejected designs are preserved as `REJ-001` through `REJ-005` and SHALL not be resurrected as implementation shortcuts.

## 7. Canonical terminology

- **Main Controller:** the single coordinator after Owner kickoff; it owns decomposition, safe parallelism, dispatch, recovery, independent verification, and covered integration.
- **ChatGPT Web Worker:** a persistently identifiable web-based GPT worker managed by the Main Controller; it can have multiple task conversations over time.
- **Task:** one schedulable unit of work, GitHub-backed or local.
- **Task Conversation:** the recoverable ChatGPT Web conversation bound to one task, retained after completion by default.
- **Batch-autonomy grant:** one Owner-confirmed Goal plus policy/authority envelope, coordinator identity, scope, validity, and optional coordinator-only actions such as `GITHUB_MERGE`.
- **True Blocker:** only an intent/scope change, security/governance weakening, new irreversible external effect, release/production/public commitment, or materially unknowable authority/truth state.
- **Completion:** independently verified physical completion plus the source-specific terminal condition defined by `REQ-016` or `REQ-017`.

## 8. Change delta

Mode: BROWNFIELD

Baseline: current Dev MCP live tool surface on 2026-08-23 plus `Nexus-new` authority contracts at GitHub main `67521fe91e990f4e140642984c743dd50a408e84`.

### ADDED

- Add the batch-autonomy authority model and Goal-bounded grant semantics (`REQ-001`, `REQ-011`, `REQ-019`, `REQ-020`).
- Add persistent ChatGPT Web worker/runtime and task-conversation management (`REQ-003` to `REQ-005`, `REQ-014`, `REQ-015`).
- Add recursive subagent delegation with descendant authorization narrowing and end-to-end lineage (`REQ-009`, `REQ-010`).
- Add task-local blocker isolation, quiet event reporting, and source-specific completion gates (`REQ-012`, `REQ-013`, `REQ-016`, `REQ-017`).

### MODIFIED

- No existing `DIRECT_DELEGATED` observable semantics are modified. Integration contracts must be extended to recognize the new separate lane without changing the old lane. Impact: `NON_BREAKING` if old-lane tests remain unchanged and passing.

### REMOVED

- None.

### RENAMED

- None. The exact implementation enum/name for the new lane is not prescribed by this specification; the settled concept is “batch-autonomy lane.”

## 9. Scope

- Dev MCP-side orchestration needed for persistent ChatGPT Web workers and elastic concurrency.
- Task and conversation identity, persistence, recovery, queueing, and worktree isolation.
- Recursive subagent dispatch through the available Dev MCP worker surface with least-privilege descendant grants.
- Main-controller independent verification and GitHub/local completion evaluation.
- Nexus authority/contract changes required to introduce the new separate external batch-autonomy lane and optional coordinator-only merge authority.
- Failure isolation, reconciliation, and event-driven Owner escalation/reporting.

## 10. Non-goals

- Always-on cloud execution while the Owner Mac is powered off is not required (`DEC-017`).
- Replacing Nexus `CapabilityPlanner`, Workforce Admission, governed lifecycle, or production/release gates is not in scope.
- Broadening `DIRECT_DELEGATED` is explicitly rejected (`REJ-001`).
- Requiring every local task to create a GitHub Issue or PR is not allowed by the confirmed task model.
- A specific browser automation technology, browser extension, Desktop-app cloning mechanism, or DevSpace Ultra code copy is not prescribed.
- Production deployment, release approval, public claims, secret-policy redesign, or cloud-hosting architecture are outside this specification.

## 11. User and operator stories

1. The Owner confirms one bounded Goal. The Main Controller sees four independent Issues, dispatches four persistent ChatGPT Web workers in parallel, and stays quiet until completion or a True Blocker.
2. A worker discovers a bounded repair needed to finish its task and delegates it to an approved subagent. The child gets only the minimum authority needed, and the Main Controller can later reconstruct the full lineage.
3. One worker loses its browser/session around a possibly successful push. The controller reconnects or reconciles Git and provider state before replacement, avoiding a duplicate push or lost candidate.
4. A worker finishes a PR. The Main Controller independently rechecks the physical diff and applicable verification, then merges without another Owner prompt only when the kickoff grant explicitly contains `GITHUB_MERGE` and fresh merge gates pass.
5. A local task has no GitHub object. The worker completes the implementation in an isolated worktree; the controller verifies the physical result and tests, accepts the scoped local deliverable, and reports completion without fabricating an Issue.

## 12. Architecture and authority boundaries

The specification requires logical responsibilities, not a brittle class/module layout:

- **Batch grant validator:** binds Goal, repository/project scope, Main Controller identity, allowed actions, expiry/revocation, Owner-only boundaries, and optional coordinator-only merge authority.
- **Main Controller orchestration:** derives child tasks, analyzes safe parallelism, schedules/queues workers, receives descendant lineage, and owns completion/blocker reporting.
- **Web worker runtime adapter and registry:** manages persistent worker identity plus task-specific conversation binding and recovery.
- **Workspace isolation adapter:** acquires isolated worktrees for mutating parallel tasks and preserves unrelated dirty state.
- **Delegation/authorization ledger:** issues narrower child authorizations and preserves complete ancestry/evidence.
- **Reconciliation service:** resolves uncertain worker, filesystem, Git, provider, and conversation state before replay or replacement.
- **Independent verification/integration coordinator:** remains separate from implementers; it alone may exercise covered coordinator-only integration authority.

The batch-autonomy lane is outside Nexus runtime. It SHALL NOT become a second Nexus planner/router or bypass Nexus when a task actually requires governed runtime authority. Existing Nexus and repository merge/claim/production boundaries remain authoritative. A task crossing such a boundary stops locally and requires the applicable Owner/authority decision; the rest of the batch continues when independent.

## 13. Requirements

### REQ-001 — Separate batch-autonomy authority lane

- **Status:** `SETTLED`
- **Source:** `DEC-001, CON-001, CON-002, REJ-001`
- **Behavior:** The system SHALL add a separate lightweight batch-autonomy authority lane for one-kickoff autonomous parallel orchestration and SHALL leave existing DIRECT_DELEGATED semantics unchanged.
- **Failure behavior:** If a request cannot be proven to fit the batch-autonomy lane, the system SHALL fail closed for that task and SHALL NOT silently reinterpret DIRECT_DELEGATED or another lane.
- **Rationale:** Preserves existing narrow safety semantics while enabling the confirmed multi-worker workflow.
- **Authority/interface:** Nexus authority contracts
- **Non-goal linkage:** Section 10: no implicit weakening of existing lanes.

### REQ-002 — One-kickoff main-controller autonomy

- **Status:** `SETTLED`
- **Source:** `DEC-010, DEC-009, DEC-011, DEC-024`
- **Behavior:** After one Owner kickoff confirmation, the Main Controller SHALL autonomously decompose, parallelize, dispatch, track, retry, reassign, reconcile, and independently verify work until Completion or a True Blocker.
- **Failure behavior:** Routine engineering failures SHALL NOT require Owner confirmation; a True Blocker SHALL pause only the affected task and surface the minimum Owner decision needed.
- **Rationale:** Implements the requested low-interruption operating model.
- **Authority/interface:** Main Controller orchestration
- **Non-goal linkage:** none

### REQ-003 — Elastic parallel worker pool

- **Status:** `SETTLED`
- **Source:** `DEC-006, DEC-008, DEC-020`
- **Behavior:** The Main Controller SHALL elastically scale active ChatGPT Web Workers to the safely parallelizable workload up to a configurable maximum concurrency, and SHALL queue excess ready work beyond that maximum.
- **Failure behavior:** The controller SHALL NOT start tasks concurrently when known dependencies or mutation overlap make parallel execution unsafe.
- **Rationale:** Four workers are an example, not a fixed product limit.
- **Authority/interface:** Worker-pool scheduler
- **Non-goal linkage:** none

### REQ-004 — Persistent worker identity

- **Status:** `SETTLED`
- **Source:** `DEC-007, DEC-013, DEC-017`
- **Behavior:** Each ChatGPT Web Worker SHALL have a durable independent worker identity that can be rediscovered after controller or browser restart within the supported local-runtime lifetime.
- **Failure behavior:** If worker identity cannot be safely rebound, the controller SHALL treat the worker as unavailable and use the recovery procedure rather than guessing its state.
- **Rationale:** Supports reusable workers without conflating tasks.
- **Authority/interface:** Web worker registry
- **Non-goal linkage:** none

### REQ-005 — Task-scoped recoverable conversations

- **Status:** `SETTLED`
- **Source:** `DEC-013, DEC-023`
- **Behavior:** Each task SHALL bind to its own recoverable ChatGPT Web conversation, independent of the persistent worker identity, and the same task SHALL preferentially resume its original conversation when work continues or reopens.
- **Failure behavior:** The system SHALL NOT append unrelated tasks indefinitely into one shared worker conversation when an independent task conversation can be created.
- **Rationale:** Provides context continuity and task isolation.
- **Authority/interface:** Conversation registry
- **Non-goal linkage:** none

### REQ-006 — Task abstraction supports GitHub and local work

- **Status:** `SETTLED`
- **Source:** `DEC-014, DEC-025`
- **Behavior:** The orchestration task model SHALL support GitHub-backed work and purely local work without requiring every task to have an Issue or PR identity.
- **Failure behavior:** The absence of a GitHub Issue or PR SHALL NOT by itself block an otherwise authorized local task.
- **Rationale:** GitHub is a task source, not the task abstraction.
- **Authority/interface:** Task model
- **Non-goal linkage:** none

### REQ-007 — Mutation isolation with worktrees

- **Status:** `SETTLED`
- **Source:** `DEC-015, CON-001`
- **Behavior:** Every concurrently mutating Git task SHALL execute in its own isolated worktree; read-only research or review MAY share a checkout when no mutation or dirty-state collision can occur.
- **Failure behavior:** If safe non-overlap cannot be established, the system SHALL create or select an isolated worktree before mutation and SHALL preserve unrelated dirty state.
- **Rationale:** Prevents cross-task filesystem and Git contamination.
- **Authority/interface:** Workspace/worktree manager
- **Non-goal linkage:** none

### REQ-008 — Dev MCP engineering capability envelope

- **Status:** `SETTLED`
- **Source:** `DEC-016, CUR-001`
- **Behavior:** A ChatGPT Web Worker SHALL be able to perform authorized engineering work up to the current live Dev MCP capability envelope, including applicable file operations, verification commands, durable subagent actions, scoped commit, and non-default-branch push.
- **Failure behavior:** The worker SHALL fail closed when a required live Dev MCP action is absent, stale, denied, or outside its child authorization; it SHALL NOT substitute broader authority merely to emulate a missing typed action.
- **Rationale:** Web workers are intended to be real engineering workers rather than reasoning-only chats.
- **Authority/interface:** Dev MCP adapter/tool bridge
- **Non-goal linkage:** Section 10: no broad shell or authority substitution.

### REQ-009 — Recursive subagent delegation with full lineage

- **Status:** `SETTLED`
- **Source:** `DEC-005, DEC-018`
- **Behavior:** A ChatGPT Web Worker MAY autonomously delegate bounded subwork to approved subagents, and the system SHALL durably record the complete parent-child-grandchild dispatch, authorization, action, evidence, and result lineage back to the originating Goal and Main Controller.
- **Failure behavior:** Untracked descendant work or descendant results that cannot be causally rebound to the originating Goal SHALL NOT be accepted as completion evidence.
- **Rationale:** Preserves recursive autonomy with centralized accountability.
- **Authority/interface:** Delegation ledger and worker adapters
- **Non-goal linkage:** none

### REQ-010 — Monotonically narrowing descendant authority

- **Status:** `SETTLED`
- **Source:** `DEC-005, REJ-005`
- **Behavior:** Every descendant dispatch SHALL receive a newly bounded child authorization whose permissions are a subset of its parent authorization; authority SHALL only narrow and SHALL never expand through delegation.
- **Failure behavior:** A descendant request for merge, final acceptance, Owner-only decisions, or any permission not present in its parent authorization SHALL be denied and surfaced to the Main Controller.
- **Rationale:** Enforces least privilege and limits blast radius.
- **Authority/interface:** Authorization/grant propagation
- **Non-goal linkage:** none

### REQ-011 — Goal-bounded dynamic child tasks

- **Status:** `SETTLED`
- **Source:** `DEC-003, REJ-003`
- **Behavior:** The batch-autonomy grant SHALL bind one Owner-confirmed Goal plus an explicit policy and authority envelope, and the Main Controller MAY create necessary child tasks dynamically when each child remains causally within that Goal.
- **Failure behavior:** A child task that changes product intent, widens scope beyond the grant, weakens security or governance, adds a new irreversible external effect, or crosses release/production/public-claim authority SHALL become a True Blocker rather than silently inheriting authority.
- **Rationale:** Avoids fixed upfront task enumeration without losing scope control.
- **Authority/interface:** Batch grant and task lineage
- **Non-goal linkage:** none

### REQ-012 — Task-local blocker isolation

- **Status:** `SETTLED`
- **Source:** `DEC-019, DEC-024`
- **Behavior:** When one task reaches a True Blocker, the system SHALL pause only that task while independent tasks continue, and SHALL ask the Owner only the smallest decision necessary to unblock it.
- **Failure behavior:** The system SHALL NOT stop the entire batch solely because one task is blocked unless a shared dependency makes continued execution unsafe.
- **Rationale:** Maintains useful progress while preserving Owner authority.
- **Authority/interface:** Batch scheduler and escalation
- **Non-goal linkage:** none

### REQ-013 — Quiet event-driven Owner reporting

- **Status:** `SETTLED`
- **Source:** `DEC-022`
- **Behavior:** Normal execution SHALL remain quiet to the Owner; the Main Controller SHALL report task or batch details when work reaches Completion or when a True Blocker requires Owner input.
- **Failure behavior:** Routine progress events, retries, CI failures, merge conflicts, worker swaps, and subagent activity SHALL remain controller-internal unless they cause a True Blocker.
- **Rationale:** Matches the requested low-interruption UX.
- **Authority/interface:** Owner notification/reporting interface
- **Non-goal linkage:** none

### REQ-014 — Worker loss recovery and reconciliation

- **Status:** `SETTLED`
- **Source:** `DEC-021, CON-002`
- **Behavior:** On ChatGPT Web Worker loss or uncertain response, the Main Controller SHALL first attempt to restore the original worker and task conversation; if restoration is impossible, it SHALL reconcile durable conversation, filesystem, Git, provider, and action state before assigning a replacement.
- **Failure behavior:** The system SHALL NOT blindly replay a possibly mutating action after timeout, disconnect, or ambiguous completion, and independent workers SHALL continue when safe.
- **Rationale:** Prevents duplicate or lost effects during recovery.
- **Authority/interface:** Recovery/reconciliation service
- **Non-goal linkage:** none

### REQ-015 — Long-term task conversation retention

- **Status:** `SETTLED`
- **Source:** `DEC-023`
- **Behavior:** Completed task conversations SHALL be retained by default for future reopen, regression investigation, or continuation until manual cleanup or a future explicit retention policy supersedes this requirement.
- **Failure behavior:** Automated cleanup SHALL NOT delete a completed task conversation without an explicit policy that preserves required task and evidence lineage.
- **Rationale:** Preserves the task context the Owner explicitly wants to keep.
- **Authority/interface:** Conversation persistence
- **Non-goal linkage:** Section 10: no mandatory cloud retention.

### REQ-016 — GitHub completion semantics

- **Status:** `SETTLED`
- **Source:** `DEC-011, DEC-012, CON-001`
- **Behavior:** For GitHub-backed work, the Main Controller SHALL report Completion only when the authorized requested result is independently verified and either the Issue is closed or the corresponding PR is merged and closed; an unmerged closed PR SHALL NOT count as success.
- **Failure behavior:** A worker report, green subset, open PR, or unmerged closed PR SHALL NOT by itself satisfy Completion.
- **Rationale:** Makes visible GitHub terminal state agree with independently verified work.
- **Authority/interface:** GitHub status and completion evaluator
- **Non-goal linkage:** none

### REQ-017 — Local completion semantics

- **Status:** `SETTLED`
- **Source:** `DEC-025`
- **Behavior:** For local work, the Main Controller SHALL report Completion only when the requested result physically exists, applicable tests or verifiers pass, and the controller independently inspects the result; mutating Git work SHALL leave a scoped commit or another explicitly requested local deliverable.
- **Failure behavior:** Worker self-report, process exit zero, or a passing subset that does not exercise the requested behavior SHALL NOT satisfy Completion.
- **Rationale:** Provides a completion definition without forcing local work into GitHub.
- **Authority/interface:** Local completion evaluator
- **Non-goal linkage:** none

### REQ-018 — Independent acceptance and non-self-approval

- **Status:** `SETTLED`
- **Source:** `DEC-012, CON-001, CON-002, CON-003`
- **Behavior:** Implementing workers and descendant agents SHALL remain candidate producers only; the Main Controller SHALL independently inspect physical effects and rerun applicable verification before final acceptance or integration.
- **Failure behavior:** No worker or descendant agent SHALL approve, merge, integrate, or claim correctness solely from its own implementation or reported PASS.
- **Rationale:** Preserves separation between implementation and acceptance.
- **Authority/interface:** Verification and integration coordinator
- **Non-goal linkage:** none

### REQ-019 — Optional kickoff GITHUB_MERGE authority

- **Status:** `SETTLED`
- **Source:** `DEC-004, REJ-004, CON-001`
- **Behavior:** The batch-autonomy grant MAY explicitly include GITHUB_MERGE for one exact repository, Goal, Main Controller, action scope, and validity window; when present, only the Main Controller SHALL exercise it after fresh independent acceptance and merge-gate verification.
- **Failure behavior:** If GITHUB_MERGE is absent, expired, revoked, scope-mismatched, or merge gates fail, merge SHALL fail closed and SHALL NOT be delegated or inferred from worker success.
- **Rationale:** Allows end-to-end completion without redundant Owner approval while preserving merge safety.
- **Authority/interface:** Batch grant validator and GitHub integration seam
- **Non-goal linkage:** none

### REQ-020 — Outside-Nexus routine execution boundary

- **Status:** `SETTLED`
- **Source:** `DEC-002, CON-003, REJ-002, CUR-002`
- **Behavior:** Routine batch-autonomy execution through DevSpace and ChatGPT Web SHALL remain outside Nexus runtime; CapabilityPlanner routing and Nexus Workforce Admission SHALL NOT be invoked solely because external orchestration uses multiple workers or descendants.
- **Failure behavior:** When an individual task crosses a governed or Owner-only boundary, the system SHALL stop that task at the boundary and SHALL NOT silently relabel or auto-enter Nexus governed execution without the required authority.
- **Rationale:** Preserves CapabilityPlanner as sole Nexus-runtime route authority without making routine external orchestration heavy.
- **Authority/interface:** DevSpace/Nexus integration boundary
- **Non-goal linkage:** Section 10: no parallel route authority.

### REQ-021 — Owner-only boundary minimization

- **Status:** `SETTLED`
- **Source:** `DEC-024, CON-001`
- **Behavior:** Owner interruption SHALL be limited to changes in intent or scope, security or governance weakening, new irreversible external effects, release or production or public commitments, and materially unknowable authority or truth states.
- **Failure behavior:** Implementation choices, ordinary bugs, test failures, lint failures, merge conflicts, worker timeouts, worker replacement, review fixes, CI reruns, and other routine engineering work SHALL NOT be treated as Owner-only blockers when they remain inside the grant.
- **Rationale:** Prevents the workflow from degrading back into repeated approvals.
- **Authority/interface:** Escalation policy
- **Non-goal linkage:** none

### REQ-022 — Preserve existing narrow lane and rejected heavy alternatives

- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-002, DEC-003, DEC-004, DEC-005, CUR-003, REJ-001, REJ-002, REJ-003, REJ-004, REJ-005`
- **Behavior:** The implementation SHALL preserve the settled governance choices: separate batch-autonomy authority, external routine execution, Goal-bounded dynamic children, optional coordinator-only kickoff merge authority, and monotonically narrowing descendant authorization.
- **Failure behavior:** The implementation SHALL NOT satisfy this specification by broadening DIRECT_DELEGATED, forcing all child work through Nexus runtime, freezing the kickoff task list, requiring redundant merge approval, or granting descendants the full batch authority.
- **Rationale:** Prevents reintroduction of explicitly rejected governance designs.
- **Authority/interface:** Cross-cutting architecture and policy
- **Non-goal linkage:** none

## 14. Behavioral and interface decisions

A task lifecycle must distinguish at minimum: queued, active, paused-on-True-Blocker, uncertain/reconciling, candidate-ready, independently-verified, completed, and failed/cancelled. Exact enum names are implementation detail. Conversation lifecycle is independent of task terminal state: a completed task conversation remains retained and reopenable. Worker identity is also independent from conversation identity: a persistent worker can host different task conversations over time.

Every mutating dispatch needs a stable task identity, attempt identity, Goal lineage, worker identity, workspace/worktree identity, authorization digest, and expected base/HEAD where applicable. Nested dispatch adds parent task/agent and child-authorization identities. Uncertain mutation must enter reconciliation before retry. Idempotency and attempt fencing must be strong enough that a lost acknowledgment cannot produce duplicate commit/push/effect.

The new external batch lane does not automatically inherit Nexus runtime task/lifecycle semantics. If a task crosses into governed Nexus work, the controller stops at that boundary and the subsequent governed flow must acquire its own valid authority and fresh transport/admission evidence.

## 15. Verification seam

The highest meaningful seam is a live authenticated macOS/browser + live Dev MCP canary for persistent ChatGPT Web worker creation, task-conversation recovery, engineering actions, concurrent isolated worktrees, descendant delegation, and restart/reconciliation. Governance and grant rules should additionally have deterministic fixture/property tests because live success alone cannot prove negative authority constraints. GitHub integration requires controlled live-canary or real-repository evidence bound to exact PR/head/base/check/grant identities. Production evidence is neither required nor authorized by this spec.

False-green defenses include: use an unmerged closed PR; remove one grant permission; kill a worker after a mutation but before acknowledgment; inject an off-Goal child task; attempt descendant `GITHUB_MERGE`; corrupt a conversation binding; omit a verifier; and run two mutating tasks with intentionally conflicting workspace targets. None of these cases may be reported as successful completion.

## 16. Acceptance criteria

### AC-001 — Existing lane remains narrow

- **Requirement:** `REQ-001`
- **Evidence level:** `FIXTURE`
- **Verification seam:** Authority-policy parser plus execution-lane contract tests
- **Pass:** A batch-autonomy grant is recognized by the new lane while a DIRECT_DELEGATED request still enforces exactly one bounded worker and no auto-chain.
- **Negative control:** Attempt to run two workers or recursive delegation under DIRECT_DELEGATED and prove it is rejected rather than silently accepted.
- **Fail:** DIRECT_DELEGATED accepts multi-worker or auto-chain behavior, or the batch grant is interpreted as DIRECT_DELEGATED.
- **Receipt binding:** Bind policy/contract revision and test fixture hash.

### AC-002 — One kickoff runs through routine engineering

- **Requirement:** `REQ-002`
- **Evidence level:** `CANARY`
- **Verification seam:** End-to-end controller canary on a bounded non-production goal
- **Pass:** After one kickoff authorization the controller completes decomposition, dispatch, retries or fixes, independent verification, and final result without routine Owner prompts.
- **Negative control:** Inject a recoverable test failure and worker retry; no Owner prompt occurs unless the injected condition crosses the True Blocker definition.
- **Fail:** Routine engineering causes an Owner prompt or controller stops before exhausting authorized recovery.
- **Receipt binding:** Bind Goal ID, grant hash, task IDs, attempt IDs, and final evidence receipt.

### AC-003 — Elastic concurrency and queueing

- **Requirement:** `REQ-003`
- **Evidence level:** `CANARY`
- **Verification seam:** Scheduler canary with independent and dependent tasks
- **Pass:** With maximum concurrency at least four, four independent ready tasks can be active concurrently; when ready tasks exceed the configured maximum, excess tasks remain queued until capacity opens.
- **Negative control:** Include at least one dependency-coupled task and prove it is not launched concurrently before its prerequisite.
- **Fail:** Scheduler exceeds maximum concurrency, serializes independent work without cause, or violates known dependency ordering.
- **Receipt binding:** Bind scheduler config, task graph, start/end timestamps, and worker IDs.

### AC-004 — Persistent worker re-discovery

- **Requirement:** `REQ-004`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** Authenticated ChatGPT Web runtime restart/reconnect gate
- **Pass:** A worker created before controller or browser-process restart can be rediscovered by durable worker identity and reused when its session remains valid.
- **Negative control:** Remove or corrupt the worker binding and prove the controller refuses to guess an identity.
- **Fail:** A valid worker cannot be rediscovered, or an ambiguous binding is accepted as the wrong worker.
- **Receipt binding:** Bind worker ID, browser/runtime instance, conversation IDs, and reconnect timestamps.

### AC-005 — Task conversation isolation and resume

- **Requirement:** `REQ-005`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** Two-task conversation binding and reopen gate
- **Pass:** Two tasks assigned to the same persistent worker have distinct conversation bindings, and reopening one task resumes its original conversation with its prior task context intact.
- **Negative control:** Attempt to resume task A using task B conversation and prove the mismatch is rejected.
- **Fail:** Tasks share an unintended conversation or task reopen creates unrelated context when the original binding is available.
- **Receipt binding:** Bind task ID, worker ID, conversation ID, and stored binding digest.

### AC-006 — GitHub and local task parity

- **Requirement:** `REQ-006`
- **Evidence level:** `SIMULATION`
- **Verification seam:** Task-model fixture plus controller integration test
- **Pass:** The controller accepts one GitHub-backed task and one local task through the same task lifecycle while preserving source-specific metadata.
- **Negative control:** Create a valid local task with no GitHub identity and prove it is not rejected for missing Issue/PR fields.
- **Fail:** Task model requires GitHub identity for local work or loses GitHub identity for GitHub-backed work.
- **Receipt binding:** Bind task schema revision and fixture IDs.

### AC-007 — Parallel mutation isolation

- **Requirement:** `REQ-007`
- **Evidence level:** `CANARY`
- **Verification seam:** Two mutating tasks in separate managed worktrees
- **Pass:** Two concurrently mutating tasks start from recorded bases, modify their own worktrees, and produce no cross-task dirty paths or branch contamination.
- **Negative control:** Deliberately attempt to target the other task worktree or overlapping unrelated dirty state and prove mutation is denied or isolated.
- **Fail:** A task changes another task worktree, absorbs unrelated dirty state, or concurrent edits become indistinguishable.
- **Receipt binding:** Bind worktree paths, base HEADs, branch names, changed-path sets, and final commits.

### AC-008 — Web worker exercises Dev MCP engineering surface

- **Requirement:** `REQ-008`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** Authenticated web-worker engineering canary using live Dev MCP
- **Pass:** A ChatGPT Web Worker can perform an authorized bounded sequence that reads code, edits within scope, runs verification, creates a scoped commit, and pushes a non-default branch using the current live Dev MCP surface.
- **Negative control:** Remove one required typed action or authorization and prove the worker fails closed rather than using an unauthorized substitute.
- **Fail:** Worker cannot perform the bounded engineering sequence or bypasses missing/denied typed actions.
- **Receipt binding:** Bind Dev MCP tool-manifest snapshot, worker/task ID, worktree, commit SHA, push ref, and verifier evidence.

### AC-009 — Nested delegation lineage is complete

- **Requirement:** `REQ-009`
- **Evidence level:** `CANARY`
- **Verification seam:** Three-level controller to web worker to subagent dispatch canary
- **Pass:** A parent worker delegates at least one bounded subtask and the Main Controller can reconstruct every parent-child edge, authorization, action/result summary, and evidence reference back to the Goal.
- **Negative control:** Delete or alter one lineage edge in the fixture and prove the result becomes non-claimable.
- **Fail:** A descendant result is accepted without complete causal lineage to the Goal.
- **Receipt binding:** Bind Goal ID, task IDs, agent IDs, parent IDs, authorization hashes, and evidence digests.

### AC-010 — Descendant authority can only narrow

- **Requirement:** `REQ-010`
- **Evidence level:** `SIMULATION`
- **Verification seam:** Authorization propagation property tests
- **Pass:** For generated descendant grants, every effective permission set is a subset of its parent and coordinator-only capabilities are absent at every descendant depth.
- **Negative control:** Attempt to mint a child with GITHUB_MERGE, final acceptance, or a permission absent from the parent and prove validation fails.
- **Fail:** Any child gains authority not present in its parent or receives non-delegable coordinator powers.
- **Receipt binding:** Bind parent/child grant hashes and policy revision.

### AC-011 — Dynamic child tasks stay inside Goal

- **Requirement:** `REQ-011`
- **Evidence level:** `SIMULATION`
- **Verification seam:** Goal-lineage and grant-envelope decision tests
- **Pass:** The controller can create an unlisted repair child task that is causally necessary for the authorized Goal and inside the grant without Owner reapproval.
- **Negative control:** Create an off-Goal or scope-widening child and prove it is classified as a True Blocker rather than auto-authorized.
- **Fail:** Legitimate within-Goal child tasks require redundant approval or off-Goal children inherit the batch grant.
- **Receipt binding:** Bind Goal definition hash, child task lineage, and grant decision receipt.

### AC-012 — One blocker does not stop independent work

- **Requirement:** `REQ-012`
- **Evidence level:** `CANARY`
- **Verification seam:** Parallel batch with one injected Owner-only blocker
- **Pass:** When one task hits a True Blocker, that task pauses and emits one minimal escalation while independent tasks continue to terminal states.
- **Negative control:** Inject a shared prerequisite blocker and prove only actually dependent tasks stop.
- **Fail:** Whole batch stops for a task-local blocker, or affected task continues across the boundary without Owner authority.
- **Receipt binding:** Bind task graph, blocker classification, escalation receipt, and sibling task timelines.

### AC-013 — Owner receives only completion or true-blocker events

- **Requirement:** `REQ-013`
- **Evidence level:** `SIMULATION`
- **Verification seam:** Notification event-stream tests
- **Pass:** Routine retries, CI failures, worker swaps, and subagent actions produce controller-internal events but no Owner notification; completion and True Blocker events produce detailed Owner-facing reports.
- **Negative control:** Feed a routine recoverable failure and verify no Owner event is emitted; feed a True Blocker and verify exactly one actionable escalation is emitted.
- **Fail:** Owner is spammed with routine progress or a True Blocker/completion is not reported.
- **Receipt binding:** Bind event schema revision and event IDs.

### AC-014 — Recovery reconciles before replacement or replay

- **Requirement:** `REQ-014`
- **Evidence level:** `CANARY`
- **Verification seam:** Kill or disconnect a mutating web worker around an uncertain action
- **Pass:** After loss, the controller first rebinds the original worker/conversation or reconciles physical state before replacement; no duplicate commit, push, or file mutation occurs.
- **Negative control:** Kill the worker after an effect but before acknowledgment and prove the effect is discovered rather than replayed blindly.
- **Fail:** A mutation is duplicated, lost, or replaced without reconciliation of uncertain state.
- **Receipt binding:** Bind task/attempt IDs, pre/post HEAD, action idempotency key, worker/conversation IDs, and reconciliation receipt.

### AC-015 — Completed conversation survives normal cleanup cycle

- **Requirement:** `REQ-015`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** Completion then later reopen/reconnect retention gate
- **Pass:** A completed task conversation remains discoverable and can be reopened after the task is terminal and after a normal controller restart, unless explicitly manually cleaned.
- **Negative control:** Run routine worker/task cleanup and prove retained completed conversation binding is not deleted.
- **Fail:** Completed task conversation disappears without manual cleanup or explicit superseding retention policy.
- **Receipt binding:** Bind task ID, conversation ID, completion timestamp, retention metadata, and reopen timestamp.

### AC-016 — GitHub terminal state is not false completion

- **Requirement:** `REQ-016`
- **Evidence level:** `CANARY`
- **Verification seam:** GitHub issue/PR completion evaluator against controlled states
- **Pass:** A merged-and-closed PR or closed Issue with independent verification can reach Completion.
- **Negative control:** Provide an unmerged closed PR, open PR, worker PASS, or pre-merge green subset and prove Completion is denied.
- **Fail:** Any negative-control state is reported as complete, or independently verified merged work is not recognized.
- **Receipt binding:** Bind repository, Issue/PR IDs, head/base/merge SHA, close/merge state, verification evidence, and evaluation timestamp.

### AC-017 — Local task requires physical result and verifier evidence

- **Requirement:** `REQ-017`
- **Evidence level:** `CANARY`
- **Verification seam:** Local mutating task completion gate
- **Pass:** A local task reaches Completion only after requested files/effects exist, applicable verifiers pass, controller independently inspects the result, and scoped Git output is present when required.
- **Negative control:** Return worker PASS with missing physical effect or skip a required verifier and prove Completion is denied.
- **Fail:** Local task completes from report text or process status without physical and independent evidence.
- **Receipt binding:** Bind worktree, before/after state, changed paths, verifier results, controller review receipt, and commit/deliverable identity.

### AC-018 — Implementer cannot self-accept

- **Requirement:** `REQ-018`
- **Evidence level:** `SIMULATION`
- **Verification seam:** Acceptance authority tests
- **Pass:** A worker-produced candidate requires a distinct Main Controller acceptance step that re-reads physical effects and applicable verification before integration.
- **Negative control:** Have the worker attempt to mark its own result accepted or merged and prove the operation is rejected.
- **Fail:** Worker self-report or self-approval can transition directly to accepted/integrated state.
- **Receipt binding:** Bind implementer identity, reviewer/controller identity, candidate SHA, and acceptance receipt.

### AC-019 — Kickoff merge grant is exact and non-delegable

- **Requirement:** `REQ-019`
- **Evidence level:** `CANARY`
- **Verification seam:** Covered and uncovered GitHub merge gate scenarios
- **Pass:** With a current exact kickoff grant that includes GITHUB_MERGE and fresh merge gates passing, the Main Controller can merge without another Owner prompt.
- **Negative control:** Omit GITHUB_MERGE, expire/revoke the grant, change Goal/repo/coordinator, fail a required check, or ask a descendant to merge; every case must fail closed.
- **Fail:** Merge succeeds outside exact grant and gate conditions or requires redundant Owner approval inside them.
- **Receipt binding:** Bind grant hash, repository, Goal, controller identity, PR/head/base, checks, acceptance, expected-head/CAS, and merge receipt.

### AC-020 — Routine external batch does not invoke Nexus routing

- **Requirement:** `REQ-020`
- **Evidence level:** `SIMULATION`
- **Verification seam:** Control-plane routing/admission instrumentation
- **Pass:** A routine external batch can dispatch and execute through DevSpace/ChatGPT Web without CapabilityPlanner or Nexus Workforce Admission events solely due to multi-worker orchestration.
- **Negative control:** Create a task that truly crosses a governed boundary and prove the affected task stops for authority rather than silently bypassing Nexus or auto-switching lanes.
- **Fail:** Routine batch needlessly enters Nexus runtime, or a governed-boundary task proceeds without required authority.
- **Receipt binding:** Bind control-plane event log, Goal/task IDs, and any escalation decision receipt.

### AC-021 — Owner-only boundary classification

- **Requirement:** `REQ-021`
- **Evidence level:** `SIMULATION`
- **Verification seam:** Decision-table tests for blocker classification
- **Pass:** Representative routine engineering conditions are classified autonomous, while intent/scope change, security weakening, irreversible external effect, release/production/public commitment, and materially unknowable authority/truth are classified Owner-only.
- **Negative control:** Include ambiguous cases such as merge conflict, worker timeout, new API semantics, and production-data mutation to detect over- and under-escalation.
- **Fail:** Routine work triggers Owner escalation or a defined Owner-only case proceeds autonomously.
- **Receipt binding:** Bind blocker-policy revision and decision-table fixture hash.

### AC-022 — Rejected governance designs cannot satisfy the spec

- **Requirement:** `REQ-022`
- **Evidence level:** `STATIC`
- **Verification seam:** Contract and architecture conformance review plus negative fixtures
- **Pass:** The implementation contains an explicit separate batch-autonomy lane, external routine orchestration boundary, Goal-based dynamic lineage, coordinator-only optional merge, and narrowing descendant grants.
- **Negative control:** Present implementations based on broadened DIRECT_DELEGATED, full Nexus routing, fixed child lists, per-PR reapproval, or full descendant inheritance and prove conformance fails.
- **Fail:** Any rejected design passes specification conformance.
- **Receipt binding:** Bind architecture/contract revision and conformance report hash.

## 17. Traceability matrix

| Requirement | Sources | Delta | Acceptance | Evidence level | Claim ceiling | Task-card handoff group |
|---|---|---|---|---|---|---|
| `REQ-001` | `DEC-001, CON-001, CON-002, REJ-001` | ADDED | `AC-001` | `FIXTURE` | implementation/canary only; no production claim | TG-1 Authority and grant contracts |
| `REQ-002` | `DEC-010, DEC-009, DEC-011, DEC-024` | ADDED | `AC-002` | `CANARY` | implementation/canary only; no production claim | TG-3 Controller orchestration |
| `REQ-003` | `DEC-006, DEC-008, DEC-020` | ADDED | `AC-003` | `CANARY` | implementation/canary only; no production claim | TG-3 Controller orchestration |
| `REQ-004` | `DEC-007, DEC-013, DEC-017` | ADDED | `AC-004` | `LIVE_RUNTIME` | implementation/canary only; no production claim | TG-2 Web worker runtime and conversations |
| `REQ-005` | `DEC-013, DEC-023` | ADDED | `AC-005` | `LIVE_RUNTIME` | implementation/canary only; no production claim | TG-2 Web worker runtime and conversations |
| `REQ-006` | `DEC-014, DEC-025` | ADDED | `AC-006` | `SIMULATION` | implementation/canary only; no production claim | TG-3 Controller orchestration |
| `REQ-007` | `DEC-015, CON-001` | ADDED | `AC-007` | `CANARY` | implementation/canary only; no production claim | TG-4 Dev MCP execution and isolation |
| `REQ-008` | `DEC-016, CUR-001` | ADDED | `AC-008` | `LIVE_RUNTIME` | implementation/canary only; no production claim | TG-4 Dev MCP execution and isolation |
| `REQ-009` | `DEC-005, DEC-018` | ADDED | `AC-009` | `CANARY` | implementation/canary only; no production claim | TG-5 Recursive delegation lineage |
| `REQ-010` | `DEC-005, REJ-005` | ADDED | `AC-010` | `SIMULATION` | implementation/canary only; no production claim | TG-5 Recursive delegation lineage |
| `REQ-011` | `DEC-003, REJ-003` | ADDED | `AC-011` | `SIMULATION` | implementation/canary only; no production claim | TG-1 Authority and grant contracts |
| `REQ-012` | `DEC-019, DEC-024` | ADDED | `AC-012` | `CANARY` | implementation/canary only; no production claim | TG-3 Controller orchestration |
| `REQ-013` | `DEC-022` | ADDED | `AC-013` | `SIMULATION` | implementation/canary only; no production claim | TG-3 Controller orchestration |
| `REQ-014` | `DEC-021, CON-002` | ADDED | `AC-014` | `CANARY` | implementation/canary only; no production claim | TG-6 Recovery and reconciliation |
| `REQ-015` | `DEC-023` | ADDED | `AC-015` | `LIVE_RUNTIME` | implementation/canary only; no production claim | TG-2 Web worker runtime and conversations |
| `REQ-016` | `DEC-011, DEC-012, CON-001` | ADDED | `AC-016` | `CANARY` | implementation/canary only; no production claim | TG-7 Verification and completion |
| `REQ-017` | `DEC-025` | ADDED | `AC-017` | `CANARY` | implementation/canary only; no production claim | TG-7 Verification and completion |
| `REQ-018` | `DEC-012, CON-001, CON-002, CON-003` | ADDED | `AC-018` | `SIMULATION` | implementation/canary only; no production claim | TG-7 Verification and completion |
| `REQ-019` | `DEC-004, REJ-004, CON-001` | ADDED | `AC-019` | `CANARY` | implementation/canary only; no production claim | TG-1 Authority and grant contracts |
| `REQ-020` | `DEC-002, CON-003, REJ-002, CUR-002` | ADDED | `AC-020` | `SIMULATION` | implementation/canary only; no production claim | TG-1 Authority and grant contracts |
| `REQ-021` | `DEC-024, CON-001` | ADDED | `AC-021` | `SIMULATION` | implementation/canary only; no production claim | TG-1 Authority and grant contracts |
| `REQ-022` | `DEC-001, DEC-002, DEC-003, DEC-004, DEC-005, CUR-003, REJ-001, REJ-002, REJ-003, REJ-004, REJ-005` | ADDED / policy conformance | `AC-022` | `STATIC` | implementation/canary only; no production claim | TG-1 Authority and grant contracts |

## 18. Evidence and claim ceiling

- **STATIC/FIXTURE/SIMULATION** may establish grant parsing, authority monotonicity, classification, and contract conformance, but not real browser/session reliability.
- **CANARY** may establish bounded orchestration, isolation, recovery, GitHub/local completion, and merge-gate behavior under the exact tested identities.
- **LIVE_RUNTIME** is required before claiming persistent ChatGPT Web workers actually work with the current authenticated browser and Dev MCP runtime.
- **BENCHMARK** is optional and cannot substitute for correctness or safety evidence.
- **PRODUCTION** evidence and production/public claims are outside this spec. A Task Card, Candidate, passing worker, or passing validator does not itself authorize merge, release, deployment, or production claims.

## 19. Rollback and failure handling

The batch-autonomy implementation must be additive and fail closed. Existing `DIRECT_DELEGATED` remains a rollback-safe narrow lane. If the new grant, web-worker runtime, task-conversation registry, descendant authorization, or reconciliation state is unavailable or corrupt, new batch-autonomy dispatch must stop rather than fall back to broader authority.

A failed worker is recovered by original-worker/conversation rebind first, physical-state reconciliation second, and replacement only after uncertainty is resolved. A task-local True Blocker pauses only that task. Revocation or expiry of batch authority prevents new governed effects and coordinator-only merge. Unrelated dirty state, unowned worktrees, or ambiguous Git effects are preserved for investigation rather than reset, stash, clean, or overwritten.

## 20. Documentation and learning write-back

Implementation should document the new lane, grant/child-authorization schema, task/conversation/worker identity rules, recovery semantics, completion semantics, and Owner-only blocker table. Runtime observations and canary findings are evidence, not automatic canonical policy. Any new repeatable failure-prevention rule must follow the existing Nexus learning/governance write-back path rather than being silently promoted by a worker.

## 21. Risks and unknowns

- **Browser/runtime fragility:** ChatGPT Web DOM/session behavior may change; this can break worker creation or recovery even if controller logic is correct. Mitigation: adapter seam plus live reconnect canary.
- **Authenticated-session sensitivity:** browser profiles/conversation access are privileged local state. This spec does not redefine secret storage; implementation must use the narrowest existing authenticated runtime boundary and avoid inventing a second credential store without separate authority.
- **Conversation identity drift:** a UI-level conversation may be deleted, renamed, or become inaccessible. Mitigation: durable binding plus explicit unavailable state; never guess a replacement is the same conversation.
- **Concurrency conflicts:** two tasks judged independent can still touch shared generated state or external resources. Mitigation: explicit overlap/dependency checks and isolated worktrees; external-side-effect conflicts remain True Blockers when not safely reversible.
- **Current transport freshness:** Dev MCP and Nexus tool inventories can change. Task-card compilation and execution must rebind exact tool manifests and repository state.
- **No unresolved Owner decision remains.** These are implementation/evidence risks, not open product choices.

## 22. Unresolved owner decisions

none

## 23. Task-card handoff boundary

| Task group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker |
|---|---|---|---|---|---|---|---|---|---|
| TG-1 Authority and grant contracts | REQ-001, REQ-011, REQ-019, REQ-020, REQ-021, REQ-022 | AC-001, AC-011, AC-019, AC-020, AC-021, AC-022 | Separate batch-autonomy authority exists with exact Goal grant, optional coordinator merge, true-blocker boundary, and narrowing child-authority contract while DIRECT_DELEGATED remains unchanged. | Must precede mutating runtime work that relies on new authority. | Fixture/simulation plus contract conformance tests. | Policy/contract correctness only; no live worker claim. | medium | MUTATE_BOUNDED | Must rebind current GitHub main and authority files before task compilation. |
| TG-2 Web worker runtime and conversations | REQ-004, REQ-005, REQ-015 | AC-004, AC-005, AC-015 | Persistent web workers and per-task recoverable conversations survive supported reconnect/restart and remain retained after completion. | Requires TG-1 authority semantics; can develop in parallel with TG-3 once interfaces are frozen. | Authenticated LIVE_RUNTIME worker/conversation canary. | Live worker/conversation behavior for tested runtime only. | medium | MUTATE_BOUNDED | Browser/ChatGPT Web control seam must be proven on macOS. |
| TG-3 Controller orchestration | REQ-002, REQ-003, REQ-006, REQ-012, REQ-013 | AC-002, AC-003, AC-006, AC-012, AC-013 | Main Controller performs Goal-bounded decomposition, elastic parallel scheduling, queueing, blocker isolation, and quiet reporting. | Consumes TG-1 grant decisions and TG-2 worker registry interface; task model can start before live browser adapter. | Simulation plus bounded parallel CANARY. | Controller orchestration correctness under tested task graph. | medium | MUTATE_BOUNDED | No known Owner blocker. |
| TG-4 Dev MCP execution and isolation | REQ-007, REQ-008 | AC-007, AC-008 | Web worker executes authorized engineering actions through the current Dev MCP surface in isolated mutating worktrees. | Requires TG-2 web-worker tool bridge and current Dev MCP tool discovery. | Live Dev MCP + worktree CANARY/LIVE_RUNTIME. | Bounded engineering capability parity for observed tool manifest. | medium | MUTATE_BOUNDED | Dev MCP tool manifest must be rebound at execution. |
| TG-5 Recursive delegation lineage | REQ-009, REQ-010 | AC-009, AC-010 | Workers can recursively delegate bounded subwork with complete ancestry and monotonically narrowing authorization. | Requires TG-1 grant schema and available Dev MCP durable-agent actions; integrates with TG-3 controller records. | Property tests plus three-level delegation CANARY. | Delegation/authority-lineage correctness; no merge authority. | medium | MUTATE_BOUNDED | No known Owner blocker. |
| TG-6 Recovery and reconciliation | REQ-014 | AC-014 | Uncertain web-worker loss is reconciled before retry or replacement, preventing duplicate/lost effects. | Requires TG-2 conversation identity, TG-4 physical worktree/Git evidence, and TG-3 attempt identity. | Fault-injection CANARY around a mutating action. | Crash/disconnect recovery for tested failure windows. | medium | MUTATE_BOUNDED | Needs controllable browser/worker fault injection. |
| TG-7 Verification and completion | REQ-016, REQ-017, REQ-018 | AC-016, AC-017, AC-018 | Controller independently accepts candidates and reports GitHub/local Completion only from physical evidence and correct terminal state. | Depends on TG-1 authority and candidate/evidence identities from runtime groups; GitHub merge path also consumes REQ-019 from TG-1. | GitHub/local canaries plus independent acceptance checks. | Completion/acceptance claim only; not production or release. | medium | MUTATE_BOUNDED | Protected merge implementation must preserve current merge-gate contract. |

## 24. Out of scope

- Automatic cloud execution while the Owner Mac is off.
- Automatic production deployment or release/public claims.
- A second Nexus route authority or any replacement for `CapabilityPlanner`.
- Broad arbitrary shell/filesystem access as a substitute for missing typed actions.
- Worker self-approval, descendant merge authority, direct push/force-push to protected default branches, or bypass of required checks.
- Mandatory migration of all existing Agy/OpenCode sessions or historical ChatGPT conversations into the new registry.
- Copying DevSpace Ultra Windows Desktop cloning code as the prescribed implementation. Its ideas may be reference evidence, but this spec defines required behavior rather than source-code reuse.

## 25. Supersession and change history

- Initial specification synthesized 2026-08-23 from owner-confirmed upstream interview `dev-mcp-ultra-20260822` and Nexus adapter `nexus-dev-mcp-ultra-20260823`.
- No prior specification is superseded.
- Any future change to Goal/grant authority, worker completion authority, descendant inheritance, Nexus runtime boundary, merge authority, or Owner-only blocker semantics must supersede the relevant decision/requirement explicitly rather than silently rewriting this document.
