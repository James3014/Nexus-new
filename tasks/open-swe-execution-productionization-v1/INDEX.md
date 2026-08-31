# Open SWE Execution Productionization V1

- **Campaign ID:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `ACTIVATION_INTEGRATION_ACTIVE`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Source spec SHA-256:** `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`
- **Source basis snapshot:** `James3014/Nexus-new@c00c299152599a87efd831c3e146ecadd8f8b21f`; pilot evidence `764333bcbed67e5b83870d5ceeb8e9d70f7e749f`; Open SWE `4bed1112362d4ce74db86e704329fda0f3412b69`; Deep Agents `0.7.6`.
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `OPEN_SWE_INTEGRATION_CONTRACT_V1`
- **Maximum campaign claim:** Open SWE execution can be productionized incrementally behind Nexus authority; this campaign does not authorize default activation, OpenCLI retirement, merge/release authority, or production-readiness claims.

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
|---|---|---|---|---|---|---|---|---|---|---|
| G1 Feature-flagged semantic adapter | REQ-001; REQ-002; REQ-003; REQ-004; REQ-005; REQ-006 | AC-001; AC-002; AC-003; AC-004; AC-005; AC-006 | Current EIA can explicitly use Open SWE semantic execution while OpenCLI remains default. | Current main source plus pinned optional dependency contract. | Focused service/sidecar/tool-surface/replay tests. | Candidate-ready default-off adapter only. | medium | CANDIDATE | none | TASK-001 |
| G2 Portable sandbox qualification | REQ-005; REQ-007 | AC-007 | A supported non-Seatbelt backend proves credential-isolated real execution. | Accepted G1 adapter contract. | Live backend qualification. | Portable sandbox qualified; no activation. | small | VERIFY | Backend availability. | TASK-002 |
| G3 Diagnosis/repair adapter | REQ-001; REQ-003; REQ-004; REQ-006 | AC-008 | Nexus queue/replay admits Open SWE diagnosis/repair and receives Candidate only. | Accepted G1 adapter plus bounded repair interface. | Real canary plus independent Candidate verification. | Diagnosis/repair Candidate path qualified. | medium | CANDIDATE | TASK-001 acceptance. | TASK-003 |
| G4 Activation evidence portfolio | REQ-007; REQ-008 | AC-009; AC-010 | Three production-shaped canaries plus artifact-aware repair attribution are complete. | G2 portable sandbox plus G3 repair path. | Canary portfolio and independent audit. | Evidence sufficient for a separate activation decision. | medium | VERIFY | TASK-002 and TASK-003 completion. | TASK-004 |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
|---|---|---|---|---|
| REQ-001 | AC-002 | TASK-001 | TASK-001 | FULL |
| REQ-001 | AC-008 | TASK-003 | TASK-003 | FULL |
| REQ-002 | AC-001 | TASK-001 | TASK-001 | FULL |
| REQ-003 | AC-004 | TASK-001 | TASK-001 | FULL |
| REQ-003 | AC-006 | TASK-001 | TASK-001 | FULL |
| REQ-003 | AC-008 | TASK-003 | TASK-003 | FULL |
| REQ-004 | AC-002 | TASK-001 | TASK-001 | FULL |
| REQ-004 | AC-008 | TASK-003 | TASK-003 | FULL |
| REQ-005 | AC-003 | TASK-001 | TASK-001 | FULL |
| REQ-005 | AC-004 | TASK-001 | TASK-001 | FULL |
| REQ-005 | AC-007 | TASK-002 | TASK-002 | FULL |
| REQ-006 | AC-005 | TASK-001 | TASK-001 | FULL |
| REQ-006 | AC-008 | TASK-003 | TASK-003 | FULL |
| REQ-007 | AC-007 | TASK-002 | TASK-002 | FULL |
| REQ-007 | AC-009 | TASK-004 | TASK-004 | FULL |
| REQ-008 | AC-010 | TASK-004 | TASK-004 | FULL |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TASK-001 | COMPLETED | IMPLEMENTATION | TRACER_BULLET | none | none | Issue #673 terminal reconciliation | Existing External Intelligence can select an Open SWE semantic adapter explicitly while OpenCLI remains unchanged default. | Focused deterministic + tool-surface + replay tests. | Default-off semantic adapter integrated and verified. | medium | CANDIDATE | COMPLETE |
| TASK-002 | COMPLETED | PROOF | PROOF_SPIKE | TASK-001 | EVIDENCE | Qualified portable credential-isolated execution evidence | Portable credential-isolated backend passes real model qualification. | Live backend qualification. | Portable backend qualified; no activation. | small | VERIFY | COMPLETE |
| TASK-003 | COMPLETED | IMPLEMENTATION | TRACER_BULLET | TASK-001 | CONTRACT | Qualified diagnosis/repair Candidate path evidence | Diagnosis/repair uses Open SWE execution while Nexus retains queue/replay/Candidate acceptance. | Real bounded canary + independent verification. | Diagnosis/repair Candidate path qualified. | medium | CANDIDATE | COMPLETE |
| TASK-004 | COMPLETED | INTEGRATION_VERIFY | TRACER_BULLET | TASK-002; TASK-003 | EVIDENCE; EVIDENCE | G8 portfolio + G9 adjudication | Minimum three-canary portfolio and artifact-aware attribution complete. | Canary portfolio audit. | `READY_FOR_ACTIVATION_DECISION`. | medium | VERIFY | COMPLETE |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** `OPEN_SWE_INTEGRATION_CONTRACT_V1`
- **Selected frontier:** `OPEN_SWE_INTEGRATION_CONTRACT_V1`
- **Selection rationale:** G1-G9 completed the productionization evidence chain. Owner selected `ACTIVATE_OPEN_SWE_DEFAULT`; the remaining source work is one bounded activation-profile integration contract rather than another Task Card chain.
- **Exact unblock condition:** G10 source reconciliation and G11 Owner activation decision are satisfied. G12-G15 follow `OPEN_SWE_INTEGRATION_CONTRACT.md`; loaded-runtime mutation remains blocked until G16.

## 5. Campaign authority and non-goals

TASK-001 through TASK-004 are completed. The active bounded frontier is `OPEN_SWE_INTEGRATION_CONTRACT_V1` under Bootstrap Governance. Open SWE receives no route-selection, Workforce Admission, GitHub mutation, approval, release, deploy, or production-claim authority. The source-controlled activation profile may be merged under G15, but loaded-runtime activation remains a separate G16 Owner boundary. OpenCLI/OpenCode remain rollback controls and are not retired under this contract.

## 6. Supersession and change history

Compiled on 2026-08-31 from `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1` SHA-256 `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`. Pilot Candidate `764333bc...` is evidence only and is not imported as production code authority. Current completion/frontier projection was reconciled on 2026-09-01 from G1-G9 terminal evidence without rewriting the individual historical Task Card snapshots.
