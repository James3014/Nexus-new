# Open SWE Execution Productionization V1

- **Campaign ID:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `H11_CONTRACT_FROZEN_H12_ACTIVE`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Source spec SHA-256:** `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`
- **Source basis snapshot:** `James3014/Nexus-new@c00c299152599a87efd831c3e146ecadd8f8b21f`; pilot evidence `764333bcbed67e5b83870d5ceeb8e9d70f7e749f`; Open SWE `4bed1112362d4ce74db86e704329fda0f3412b69`; Deep Agents `0.7.6`.
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-005`
- **Maximum campaign claim:** `EXTERNAL_RUNTIME_CONFIRMED`; the corrective external-runtime architecture and dormant ChatGPT Web model bridge are integrated. Current work hardens explicit OpenCLI transport binding and post-integration Web qualification. No GPT Web default activation, OpenCLI retirement, release, deployment, or production-readiness claim is authorized by this state.

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
| TASK-005 | ACTIVE | IMPLEMENTATION | TRACER_BULLET | none | none | Owner-authorized Issue #695 Ready reconciliation | ChatGPT Web transport enforces explicit 1.8.7 binding, conservative pacing, bounded turns, and fail-closed retry/reconciliation behavior. | Deterministic fake-clock and negative-control tests plus exact Candidate verification. | `IMPLEMENTER_PASS_PENDING_ACCEPTANCE`. | medium | CANDIDATE | READY |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** `TASK-005`.
- **Selected frontier:** `TASK-005`.
- **Selection rationale:** the external-runtime corrective architecture is already integrated, and PR #688 integrated the dormant ChatGPT Web model bridge without changing Nexus authority. Current evidence shows the next correctness boundary is explicit controller-to-runtime binding for OpenCLI executable/profile/site-session/timeout plus post-integration runtime qualification.
- **Exact unblock condition:** bind OpenCLI transport identity explicitly through the external runtime request contract, independently accept and integrate that bounded change, then complete process-death/reconciliation and real Web semantic/diagnosis/repair witnesses before any default-activation decision.

## 5. Campaign authority and non-goals

TASK-001 through TASK-004 remain historical completed snapshots of the original productionization campaign, and their in-process dependency/runtime topology remains superseded. The corrective external-runtime architecture and dormant ChatGPT Web bridge are now integrated; the active bounded frontier is explicit OpenCLI transport binding plus post-integration Web qualification under Bootstrap Governance. Open SWE receives no route-selection, Workforce Admission, GitHub mutation, approval, release, deploy, or production-claim authority. Runtime/default activation remains a separate later gate.

## 6. Supersession and change history

Compiled on 2026-08-31 from `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1` SHA-256 `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`. Pilot Candidate `764333bc...` is evidence only and is not imported as production code authority. On 2026-09-01, a corrective Owner handoff established that Pilot import mechanics did not prove production deployment topology; `OPEN_SWE_EXTERNAL_RUNTIME_CORRECTIVE_CONTRACT.md` supersedes in-process dependency/runtime instructions while preserving the historical Task Card records and settled Nexus authority boundaries. On 2026-09-03, `NEXUS_CONTROLLER_HANDOFF_V2` plus the Owner-authorized sanitized Ready reconciliation on Issue #695 froze H11 and activated TASK-005 on current-main `dc315c38562834923729dcb45bd2b85344c35bc9`. OpenCLI `1.8.7` is an explicit Owner-approved roadmap delta from unavailable npm `1.8.8`.
