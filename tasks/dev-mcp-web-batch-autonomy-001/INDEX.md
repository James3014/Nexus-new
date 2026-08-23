# Dev MCP Persistent ChatGPT Web Batch Autonomy Campaign

- **Campaign ID:** `CAMPAIGN-DEV-MCP-WEB-BATCH-AUTONOMY-001`
- **Status:** `READY_FOR_OWNER_REVIEW`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-DEV-MCP-WEB-BATCH-AUTONOMY-001`
- **Source spec SHA-256:** `fc57f20b2133ed98c8f0c5eabcd6bbe5567aa8a3f97aef70b2eca1ba42bf9d22`
- **Source basis snapshot:** Approved spec basis plus GitHub `James3014/Nexus-new` activation base `9ff8bccff38384b83400f9cbea2747f5ce9bd8f0`; ordinary local Nexus checkout remains stale/dirty and is excluded as the mutation baseline. DevSpace source `/Users/jameschen/Workspace/devspace-chatgpt-mcp` HEAD `a086059af7095126915011dfb2ba2e19d06eff95` with four preserved dirty Agy files; live Agy smoke on CLI 1.1.19 completed read-only with no changed paths.
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-001`
- **Owner-authorized active frontier:** `TASK-001` on 2026-08-23; no sibling activation or auto-chain authority
- **Maximum campaign claim:** Owner-confirmed implementation specification with exactly one active governed frontier; no implementation, runtime readiness, release, deployment, or production claim

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
|---|---|---|---|---|---|---|---|---|---|---|
| TG-1 Authority and grant contracts | REQ-001, REQ-011, REQ-019, REQ-020, REQ-021, REQ-022 | AC-001, AC-011, AC-019, AC-020, AC-021, AC-022 | Separate batch-autonomy authority exists with exact Goal grant, optional coordinator merge, true-blocker boundary, and narrowing child-authority contract while DIRECT_DELEGATED remains unchanged. | Must precede mutating runtime work that relies on new authority. | Fixture/simulation plus contract conformance tests. | Policy/contract correctness only; no live worker claim. | medium | MUTATE_BOUNDED | TASK-001 activation rebounded to current GitHub history; execution still requires fresh main/transport/workforce binding at dispatch. | TASK-001; TASK-003 |
| TG-2 Web worker runtime and conversations | REQ-004, REQ-005, REQ-015 | AC-004, AC-005, AC-015 | Persistent web workers and per-task recoverable conversations survive supported reconnect/restart and remain retained after completion. | Requires TG-1 authority semantics; can develop in parallel with TG-3 once interfaces are frozen. | Authenticated LIVE_RUNTIME worker/conversation canary. | Live worker/conversation behavior for tested runtime only. | medium | MUTATE_BOUNDED | Browser/ChatGPT Web control seam must be proven on macOS. | TASK-002 |
| TG-3 Controller orchestration | REQ-002, REQ-003, REQ-006, REQ-012, REQ-013 | AC-002, AC-003, AC-006, AC-012, AC-013 | Main Controller performs Goal-bounded decomposition, elastic parallel scheduling, queueing, blocker isolation, and quiet reporting. | Consumes TG-1 grant decisions and TG-2 worker registry interface; task model can start before live browser adapter. | Simulation plus bounded parallel CANARY. | Controller orchestration correctness under tested task graph. | medium | MUTATE_BOUNDED | No known Owner blocker. | TASK-004 |
| TG-4 Dev MCP execution and isolation | REQ-007, REQ-008 | AC-007, AC-008 | Web worker executes authorized engineering actions through the current Dev MCP surface in isolated mutating worktrees. | Requires TG-2 web-worker tool bridge and current Dev MCP tool discovery. | Live Dev MCP + worktree CANARY/LIVE_RUNTIME. | Bounded engineering capability parity for observed tool manifest. | medium | MUTATE_BOUNDED | Dev MCP tool manifest must be rebound at execution. | TASK-005 |
| TG-5 Recursive delegation lineage | REQ-009, REQ-010 | AC-009, AC-010 | Workers can recursively delegate bounded subwork with complete ancestry and monotonically narrowing authorization. | Requires TG-1 grant schema and available Dev MCP durable-agent actions; integrates with TG-3 controller records. | Property tests plus three-level delegation CANARY. | Delegation/authority-lineage correctness; no merge authority. | medium | MUTATE_BOUNDED | No known Owner blocker. | TASK-006 |
| TG-6 Recovery and reconciliation | REQ-014 | AC-014 | Uncertain web-worker loss is reconciled before retry or replacement, preventing duplicate/lost effects. | Requires TG-2 conversation identity, TG-4 physical worktree/Git evidence, and TG-3 attempt identity. | Fault-injection CANARY around a mutating action. | Crash/disconnect recovery for tested failure windows. | medium | MUTATE_BOUNDED | Needs controllable browser/worker fault injection. | TASK-007 |
| TG-7 Verification and completion | REQ-016, REQ-017, REQ-018 | AC-016, AC-017, AC-018 | Controller independently accepts candidates and reports GitHub/local Completion only from physical evidence and correct terminal state. | Depends on TG-1 authority and candidate/evidence identities from runtime groups; GitHub merge path also consumes REQ-019 from TG-1. | GitHub/local canaries plus independent acceptance checks. | Completion/acceptance claim only; not production or release. | medium | MUTATE_BOUNDED | Protected merge implementation must preserve current merge-gate contract. | TASK-008 |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
|---|---|---|---|---|
| REQ-001 | AC-001 | TASK-001 | TASK-001 | FULL |
| REQ-002 | AC-002 | TASK-004 | TASK-004 | FULL |
| REQ-003 | AC-003 | TASK-004 | TASK-004 | FULL |
| REQ-004 | AC-004 | TASK-002 | TASK-002 | FULL |
| REQ-005 | AC-005 | TASK-002 | TASK-002 | FULL |
| REQ-006 | AC-006 | TASK-004 | TASK-004 | FULL |
| REQ-007 | AC-007 | TASK-005 | TASK-005 | FULL |
| REQ-008 | AC-008 | TASK-005 | TASK-005 | FULL |
| REQ-009 | AC-009 | TASK-006 | TASK-006 | FULL |
| REQ-010 | AC-010 | TASK-006 | TASK-006 | FULL |
| REQ-011 | AC-011 | TASK-003 | TASK-003 | FULL |
| REQ-012 | AC-012 | TASK-004 | TASK-004 | FULL |
| REQ-013 | AC-013 | TASK-004 | TASK-004 | FULL |
| REQ-014 | AC-014 | TASK-007 | TASK-007 | FULL |
| REQ-015 | AC-015 | TASK-002 | TASK-002 | FULL |
| REQ-016 | AC-016 | TASK-008 | TASK-008 | FULL |
| REQ-017 | AC-017 | TASK-008 | TASK-008 | FULL |
| REQ-018 | AC-018 | TASK-008 | TASK-008 | FULL |
| REQ-019 | AC-019 | TASK-003 | TASK-003 | FULL |
| REQ-020 | AC-020 | TASK-001 | TASK-001 | FULL |
| REQ-021 | AC-021 | TASK-003 | TASK-003 | FULL |
| REQ-022 | AC-022 | TASK-001 | TASK-001 | FULL |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TASK-001 | ACTIVE | CONTRACT | TRACER_BULLET | none | none | Owner explicitly authorized the next gate after PR #523; GitHub activation base rebound to `9ff8bccff38384b83400f9cbea2747f5ce9bd8f0`. | Current Nexus authority explicitly preserves DIRECT_DELEGATED while defining a separate external batch-autonomy lane and its outside-Nexus routing boundary. | Focused authority bootstrap tests plus context-budget guard and diff audit. | Policy/contract correctness only; no live worker claim. | medium | CANDIDATE | READY |
| TASK-002 | BLOCKED | IMPLEMENTATION | TRACER_BULLET | TASK-003 | CONTRACT | Accepted typed batch-grant primitives available to bind worker/task authority, with execution-time DevSpace source/package rebinding and macOS browser/ChatGPT Web control-seam proof before mutation. | A persistent worker identity can host separate task conversations that survive supported reconnect/restart and remain retained after completion. | Conversation persistence tests plus authenticated macOS ChatGPT Web create/resume/restart canary. | Live worker/conversation behavior for tested runtime only. | medium | CANDIDATE | READY |
| TASK-003 | BLOCKED | IMPLEMENTATION | TRACER_BULLET | TASK-001 | CONTRACT | Accepted Nexus batch-autonomy authority wording and unchanged DIRECT_DELEGATED witness, followed by execution-time DevSpace source/package rebinding and non-overlapping path freeze before mutation. | DevSpace has a typed Goal-bounded batch grant with explicit Owner-only boundaries and optional coordinator-only GITHUB_MERGE that can be validated without broadening descendant authority. | Contract fixtures, blocker decision-table simulation, grant negative controls, typecheck, and bounded diff review. | Policy/contract correctness only; no live worker claim. | medium | CANDIDATE | READY |
| TASK-004 | BLOCKED | IMPLEMENTATION | TRACER_BULLET | TASK-003; TASK-002 | CONTRACT; CONTRACT | Goal grant and Owner-only classification contract accepted.; Persistent worker/task-conversation interface accepted and revision-bound. | The Main Controller derives Goal-local tasks, schedules safe parallel work up to a configurable limit, queues excess work, isolates blockers, and emits only Completion or True Blocker owner events. | Deterministic scheduler/task-graph simulation plus bounded parallel canary and event negative controls. | Controller orchestration correctness under tested task graph. | medium | CANDIDATE | READY |
| TASK-005 | BLOCKED | IMPLEMENTATION | TRACER_BULLET | TASK-002 | CONTRACT | Accepted Web worker runtime exposes a stable task-scoped tool bridge identity, and execution-time source audit rebinds the live Dev MCP manifest and exact source seams. | A mutating Web worker receives its own managed worktree and can use only the authorized typed Dev MCP engineering actions up to the currently observed capability envelope. | Managed-worktree tests, execution-contract negative controls, candidate tests, and live Dev MCP canary. | Bounded engineering capability parity for observed tool manifest. | medium | CANDIDATE | READY |
| TASK-006 | BLOCKED | IMPLEMENTATION | TRACER_BULLET | TASK-003; TASK-004; TASK-005 | CONTRACT; CONTRACT; CONTRACT | Typed parent/child grant primitives accepted.; Controller task/attempt lineage accepted.; Web worker Dev MCP bridge can dispatch bounded durable agents with exact execution contracts. | A Web worker can delegate bounded child work while every descendant authorization is a strict subset of its parent and complete ancestry/evidence returns to the Main Controller. | Authority subset property tests, three-level delegation canary, and descendant merge/owner-action denial controls. | Delegation/authority-lineage correctness; no merge authority. | medium | CANDIDATE | READY |
| TASK-007 | BLOCKED | IMPLEMENTATION | TRACER_BULLET | TASK-002; TASK-004; TASK-005 | CONTRACT; CONTRACT; EVIDENCE | Worker/conversation identity and restoration contract accepted.; Controller task/attempt identity and scheduling state accepted.; Physical worktree/Git evidence and typed reconciliation bridge accepted. | After an uncertain worker loss, the controller rebinds or reconciles physical state before replay/replacement so duplicate or lost mutations are prevented in tested failure windows. | Fault-injection canary around post-effect/pre-ack windows plus reconcile negative controls. | Crash/disconnect recovery for tested failure windows. | medium | CANDIDATE | READY |
| TASK-008 | BLOCKED | INTEGRATION_VERIFY | TRACER_BULLET | TASK-003; TASK-004; TASK-005; TASK-007 | CONTRACT; CONTRACT; EVIDENCE; EVIDENCE | Kickoff grant and optional coordinator-only merge semantics accepted.; Controller task/result states accepted.; Candidate/worktree physical evidence bridge accepted.; Uncertain failure recovery produces reconciled attempt/effect identity. | The Main Controller independently accepts physical results and reports GitHub or local Completion only when terminal-state and verifier evidence satisfy the source specification. | GitHub/local completion canaries, independent-review identity checks, false-green negative controls, and merge-grant gate replay. | Completion/acceptance claim only; not production or release. | medium | MUTATE_BOUNDED | READY |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** TASK-001
- **Selected frontier:** TASK-001
- **Selection rationale:** TASK-001 is the only dependency-free implementation card. The Owner explicitly requested completion of the next gate after PR #523 merged, and GitHub main was rebound at activation base `9ff8bccff38384b83400f9cbea2747f5ce9bd8f0`. Downstream technical blockers are task-local and do not block TASK-001.
- **Activation boundary:** This activation selects TASK-001 only. It does not activate TASK-002 through TASK-008, does not enable parallel execution, and does not enable auto-chain.
- **Execution freshness:** Before mutation, `nexus-model-task-compiler` / executor must re-read the post-activation GitHub main HEAD, exact Task Card hash, root contracts, live Gateway/action schema, and current Workforce Admission. Any drift requires rebinding rather than using the activation-base SHA as standing authority.
- **Exact next gate:** Compile exactly TASK-001 against the fresh post-activation main and current admitted worker/transport; if any required runtime/schema/workforce binding is unavailable or stale, fail closed without starting a mutation.

## 5. Campaign authority and non-goals

This campaign now authorizes exactly `TASK-001` as the sole active governed frontier after this activation change is integrated. That authorization is bounded by the Task Card, source Spec, current Nexus lifecycle, fresh route/transport/workforce gates, and `AUTO_CHAIN=false`. It does not itself select or admit a model, authorize a sibling card, broaden scope, grant worker approval/integration/merge authority, or claim implementation/runtime/release/deployment/production readiness. Downstream blocked cards remain non-executable until their own frontier evidence is physically satisfied and they are separately activated.

## 6. Supersession and change history

Initial compilation from `SPEC-DEV-MCP-WEB-BATCH-AUTONOMY-001` SHA-256 `fc57f20b2133ed98c8f0c5eabcd6bbe5567aa8a3f97aef70b2eca1ba42bf9d22` on 2026-08-23. PR #523 integrated the Spec and eight-card campaign into GitHub main. On 2026-08-23 the Owner explicitly authorized the next gate; TASK-001 was selected as the sole ACTIVE frontier and rebound to GitHub activation base `9ff8bccff38384b83400f9cbea2747f5ce9bd8f0`. Downstream blocked cards intentionally carry no mutation paths; after their proof/dependency evidence freezes exact source seams, they must be superseded rather than silently widened.
