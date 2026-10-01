# GitHub Issue #514 CapabilitySelector containment

- **Campaign ID:** `github-issue-514-capability-selector-containment-20260822`
- **Status:** `READY_FOR_EXECUTION`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-ISSUE-514-CAPABILITY-SELECTOR-CONTAINMENT`
- **Source spec SHA-256:** `edba2af79059a98be3cfb665da74c723199870505e5b84e33eba7a36b3abc8ea`
- **Source basis snapshot:** `James3014/Nexus-new@d6b4bd77e8b559710ca103eeaa30f57b2e54fcdf`; Issue #514
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-514-001`
- **Maximum campaign claim:** `LEGACY_CAPABILITY_SELECTOR_AUTHORITY_CONTAINED_AT_SOURCE`

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
|---|---|---|---|---|---|---|---|---|---|---|
| selector-containment | REQ-001;REQ-002;REQ-003 | AC-001;AC-002;AC-003;AC-004 | Legacy production callers cannot act as a second selector. | none | focused tests + diff/scope audit | `LEGACY_CAPABILITY_SELECTOR_AUTHORITY_CONTAINED_AT_SOURCE` | medium | CANDIDATE | Nexus Gateway checkout stale; use current-base governed GitHub worktree. | TASK-514-001 |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
|---|---|---|---|---|
| REQ-001 | AC-001 | TASK-514-001 | TASK-514-001 | FULL |
| REQ-001;REQ-002 | AC-002 | TASK-514-001 | TASK-514-001 | FULL |
| REQ-003 | AC-003 | TASK-514-001 | TASK-514-001 | FULL |
| REQ-001;REQ-002;REQ-003 | AC-004 | TASK-514-001 | TASK-514-001 | FULL |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TASK-514-001 | ACTIVE | IMPLEMENTATION | TRACER_BULLET | none | none | none | Planner is sole selection authority on affected legacy paths. | focused tests + diff/scope audit | `LEGACY_CAPABILITY_SELECTOR_AUTHORITY_CONTAINED_AT_SOURCE` | medium | CANDIDATE | current-base DevSpace worktree available |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** `TASK-514-001`
- **Selected frontier:** `TASK-514-001`
- **Selection rationale:** directly retires the confirmed duplicate authority with one reviewable source/test slice.
- **Exact unblock condition:** none

## 5. Campaign authority and non-goals

Issue #514 plus this committed Task Card govern bounded implementation. `CapabilityPlanner` remains selection authority. Independent acceptance is required before merge. No approval, merge, release, runtime activation, receipt-coverage repair, or C9 claim is granted by this campaign.

## 6. Supersession and change history

Initial campaign compiled from `SPEC-ISSUE-514-CAPABILITY-SELECTOR-CONTAINMENT`; no supersession.
