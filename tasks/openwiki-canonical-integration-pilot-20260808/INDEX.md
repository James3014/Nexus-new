# OpenWiki Canonical Integration Pilot

- **Campaign ID:** `CAMPAIGN-OPENWIKI-CANONICAL-INTEGRATION-PILOT-20260808`
- **Status:** `RETAINED_FOR_REVIEW`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-OPENWIKI-CANONICAL-INTEGRATION-PILOT-20260808`
- **Source spec SHA-256:** `f07c242de66a8eb5a0c5b904c282cb03cb5b5a6678247ff4a5a7cdc13557d9e1`
- **Source basis snapshot:** `/Users/jameschen/Workspace/nexus`, `nexus/integration/main`, specification baseline HEAD `dac6e7279981828ed135f27c1c42449b0a1fd9c7`, Owner decisions through 2026-08-08
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-OPENWIKI-INTEGRATION-PILOT-01` (`RETAINED_FOR_REVIEW`)
- **Maximum campaign claim:** `OPENWIKI_PILOT_SCAFFOLD_PHYSICALLY_PRESENT_ACCEPTANCE_UNPROVEN`

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OPENWIKI-PILOT-SCAFFOLD | REQ-001; REQ-002; REQ-003; REQ-004; REQ-005; REQ-006 | AC-001; AC-002; AC-003; AC-004; AC-005; AC-006 | Repository contains a manual-only, read-only OpenWiki pilot scaffold with V3 classification and fail-closed side-effect boundaries, without generated Wiki integration. | none | static file contract + isolated Candidate diff + `git diff --check` | OPENWIKI_PILOT_SCAFFOLD_PHYSICALLY_PRESENT_ACCEPTANCE_UNPROVEN | small | not applicable | none | TASK-OPENWIKI-INTEGRATION-PILOT-01 |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
| --- | --- | --- | --- | --- |
| REQ-001 | AC-001 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | RETAINED_FOR_REVIEW |
| REQ-002 | AC-002 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | RETAINED_FOR_REVIEW |
| REQ-003 | AC-003 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | RETAINED_FOR_REVIEW |
| REQ-004 | AC-004 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | RETAINED_FOR_REVIEW |
| REQ-005 | AC-005 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | RETAINED_FOR_REVIEW |
| REQ-006 | AC-006 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | TASK-OPENWIKI-INTEGRATION-PILOT-01 | RETAINED_FOR_REVIEW |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TASK-OPENWIKI-INTEGRATION-PILOT-01 | RETAINED_FOR_REVIEW | IMPLEMENTATION | TRACER_BULLET | none | none | historical acceptance/closure/canary receipts missing | Repository contains a manual-only, read-only OpenWiki pilot scaffold with V3 classification and fail-closed side-effect boundaries, without generated Wiki integration. | static file contract + isolated Candidate diff + `git diff --check` | OPENWIKI_PILOT_SCAFFOLD_PHYSICALLY_PRESENT_ACCEPTANCE_UNPROVEN | small | not applicable | NOT_APPLICABLE |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** none; the task is `RETAINED_FOR_REVIEW`
- **Selected frontier:** `TASK-OPENWIKI-INTEGRATION-PILOT-01`
- **Selection rationale:** The single tracer-bullet scaffold is physically
  present, but historical acceptance, closure, and canary receipts are absent.
- **Exact unblock condition:** Reconcile the missing validator-supported
  acceptance and closure evidence through the Owner/independent review gate.

## 5. Campaign authority and non-goals

The Git-tracked active Task Card is execution authority for the bounded implementation Candidate only.

CapabilityPlanner and HybridRouteDecision remain route authority.

OpenWiki remains derived and non-authoritative.

Agy may produce the bounded Candidate but may not approve, integrate, push, release, or make production/public claims.

`AUTO_CHAIN=false`.

## 6. Supersession and change history

2026-08-08: Supersedes the simplified campaign identity `openwiki-canonical-integration-pilot-20260808` while preserving its approved three-file implementation scope.

The simplified Task ID `OPENWIKI-INTEGRATION-PILOT-01` is superseded by `TASK-OPENWIKI-INTEGRATION-PILOT-01`.

## Ordered Cards

1. [00-OPENWIKI-INTEGRATION-PILOT-01.md](00-OPENWIKI-INTEGRATION-PILOT-01.md) - `TASK-OPENWIKI-INTEGRATION-PILOT-01`

## Current Frontier

`TASK-OPENWIKI-INTEGRATION-PILOT-01`

## Completed Cards

- none; the scaffold is not accepted or closed

## Blocked Cards

- none; the task is retained for review pending evidence reconciliation

## Reconciliation disposition (Issue #11)

- **State:** `RETAINED_FOR_REVIEW`; this campaign is not `COMPLETED`.
- **Physical state:** `.openwikiignore`, `openwiki/INSTRUCTIONS.md`, and
  `.github/workflows/openwiki-update.yml` are physically present in the
  current tree and preserve the bounded scaffold surface.
- **Evidence gap:** Historical AC-001 through AC-006 validator output, the
  exact Candidate commit/tree receipt, independent acceptance/closure receipt,
  and manual canary receipt are not present in the current evidence surface.
- **Claim boundary:** Physical scaffold presence is evidence of scaffold
  presence only. It does not establish acceptance, closure, canary success,
  OpenWiki runtime behavior, approval, integration, or production/public
  readiness.
- **Next gate:** Owner/independent review must reconcile the missing historical
  acceptance and closure evidence before any completion or canary claim.
