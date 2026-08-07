# OpenWiki Canonical Integration Pilot

- **Campaign ID:** `CAMPAIGN-OPENWIKI-CANONICAL-INTEGRATION-PILOT-20260808`
- **Status:** `READY_FOR_EXECUTION`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-OPENWIKI-CANONICAL-INTEGRATION-PILOT-20260808`
- **Source spec SHA-256:** `f07c242de66a8eb5a0c5b904c282cb03cb5b5a6678247ff4a5a7cdc13557d9e1`
- **Source basis snapshot:** `/Users/jameschen/Workspace/nexus`, `nexus/integration/main`, specification baseline HEAD `dac6e7279981828ed135f27c1c42449b0a1fd9c7`, Owner decisions through 2026-08-08
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-OPENWIKI-INTEGRATION-PILOT-01`
- **Maximum campaign claim:** `OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY`

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OPENWIKI-PILOT-SCAFFOLD | REQ-001; REQ-002; REQ-003; REQ-004; REQ-005; REQ-006 | AC-001; AC-002; AC-003; AC-004; AC-005; AC-006 | Repository contains a manual-only, read-only OpenWiki pilot scaffold with V3 classification and fail-closed side-effect boundaries, without generated Wiki integration. | none | static file contract + isolated Candidate diff + `git diff --check` | OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY | small | not applicable | none | TASK-OPENWIKI-INTEGRATION-PILOT-01 |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
| --- | --- | --- | --- | --- |
| REQ-001 | AC-001 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | FULL |
| REQ-002 | AC-002 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | FULL |
| REQ-003 | AC-003 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | FULL |
| REQ-004 | AC-004 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | FULL |
| REQ-005 | AC-005 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | FULL |
| REQ-006 | AC-006 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | FULL |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TASK-OPENWIKI-INTEGRATION-PILOT-01 | ACTIVE | IMPLEMENTATION | TRACER_BULLET | none | none | none | Repository contains a manual-only, read-only OpenWiki pilot scaffold with V3 classification and fail-closed side-effect boundaries, without generated Wiki integration. | static file contract + isolated Candidate diff + `git diff --check` | OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY | small | not applicable | NOT_APPLICABLE |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** `TASK-OPENWIKI-INTEGRATION-PILOT-01`
- **Selected frontier:** `TASK-OPENWIKI-INTEGRATION-PILOT-01`
- **Selection rationale:** The single tracer-bullet scaffold is already Owner-approved, has no unresolved dependency or transport requirement, and establishes the containment boundary before any OpenWiki canary.
- **Exact unblock condition:** `none`

## 5. Campaign authority and non-goals

The Git-tracked active Task Card is execution authority for the bounded implementation Candidate only.

CapabilityPlanner and HybridRouteDecision remain route authority.

OpenWiki remains derived and non-authoritative.

Agy may produce the bounded Candidate but may not approve, integrate, push, release, or make production/public claims.

`AUTO_CHAIN=false`.

## 6. Supersession and change history

2026-08-08: Supersedes the simplified campaign identity `openwiki-canonical-integration-pilot-20260808` while preserving its approved three-file implementation scope.

The simplified Task ID `OPENWIKI-INTEGRATION-PILOT-01` is superseded by `TASK-OPENWIKI-INTEGRATION-PILOT-01`.
