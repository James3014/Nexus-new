# Open SWE Execution Productionization V1

- **Campaign ID:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `TASK_006_COMPLETED_AT_BOUNDED_CLAIM_CEILING`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Source spec SHA-256:** `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`
- **Source basis snapshot:** `James3014/Nexus-new@c00c299152599a87efd831c3e146ecadd8f8b21f`; pilot evidence `764333bcbed67e5b83870d5ceeb8e9d70f7e749f`; Open SWE `4bed1112362d4ce74db86e704329fda0f3412b69`; Deep Agents `0.7.6`.
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `CLOSED_AT_R28_BOUNDED_CLAIM`
- **Maximum campaign claim:** `RESIDENT_OPEN_SWE_AUTOMATION_READY_FOR_FIVE_MOUNTED_REPOSITORIES`; this requires fresh source/config/runtime/PID-bound readiness plus a harmless unattended canary. It does not approve or merge repository Candidates and does not establish release or public production readiness.

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
| TASK-005 | SUPERSEDED_AT_ACTIVATION_GATE | IMPLEMENTATION | TRACER_BULLET | none | none | Owner-authorized Issue #695 Ready reconciliation | ChatGPT Web transport enforces explicit 1.8.7 binding, conservative pacing, bounded turns, and fail-closed retry/reconciliation behavior. | Deterministic fake-clock and negative-control tests plus exact Candidate verification. | Historical hardening evidence only; its `persistent`/`very-high` activation assumptions are superseded. | medium | CANDIDATE | HISTORICAL |
| TASK-006 | COMPLETED_AT_BOUNDED_CLAIM_CEILING | INTEGRATION_ACTIVATION | TRACER_BULLET | Runtime composite/reconciliation path on runtime main `3eb673bfcfd874043a70743e34761784fda39c10` | EVIDENCE | Accepted runtime composite/reconciliation path: PRs #46/#48/#50/#53/#55 (Issues #45/#47/#49/#51/#54), plus r28 operation/effect/Candidate evidence | Resident External Intelligence completed the bounded five-mount activation witness through the accepted runtime composite/reconciliation path and controller acceptance receipt `9638ef72801a31ca84560b8b7d3d99bd512925b593f7b535b993b762b5860cf6`. | r28 operation `96b83c02de43ff8e6bc37d49e0efabd3f113ac60135ea214c367094b24806574`, durable effect `effect_ef0802c64e2a8e8f8a65ccb696adf1b0d9d50b21a06348e10d931a038d88af68`, whole verification, five-mount receipt, rollback/restore receipt, and READY run. | `RESIDENT_OPEN_SWE_AUTOMATION_READY_FOR_FIVE_MOUNTED_REPOSITORIES` at the r28 bounded ceiling. | medium | CANDIDATE | CLOSED_AT_BOUNDED_CLAIM |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** none; TASK-006 is closed at the r28 bounded claim ceiling.
- **Selected frontier:** none; the campaign is closed at the r28 documentation boundary.
- **Selection rationale:** bounded semantic and worker canaries verified the external runtime through OpenCLI/ChatGPT Web, and Issue #850 supplies the explicit Owner decision to integrate that correction into the resident service and mount five repositories.
- **TASK-006 rationale:** Issue #850 is the explicit Owner activation decision after bounded semantic and worker Web qualification. It supersedes TASK-005 activation assumptions only where live evidence selected `balanced` plus `ephemeral`; TASK-005 remains historical hardening evidence and does not itself authorize deployment.
- **Acceptance result:** controller receipt `9638ef72801a31ca84560b8b7d3d99bd512925b593f7b535b993b762b5860cf6` records `CANDIDATE_ACCEPTED_FOR_R28_ACTIVATION_WITNESS`; the acceptance packet `1b089e62d2077fbc18e96e37952128155c63cec4d07d86b798075a9fef555b93` retains its earlier pending state as historical artifact evidence.
- **Historical boundary:** Issue #906 / PR #908 was rejected and closed unmerged; no recovery from that proposal entered Nexus-new main.

## 5. Campaign authority and non-goals

TASK-001 through TASK-004 remain historical completed snapshots of the original productionization campaign, and their in-process dependency/runtime topology remains superseded. TASK-005 remains historical transport-hardening evidence; its activation assumptions are superseded by actual bounded Web qualification and the explicit Owner decision in Issue #850. TASK-006 is completed at the r28 bounded claim ceiling. Issue #895 and Issue #906 remain historical repair context; Issue #906 / PR #908 was rejected and closed unmerged, and no recovery from it entered Nexus-new main. Neither creates route, completion, acceptance, or merge authority. Open SWE receives no route-selection, Workforce Admission, approval, merge, release, or public production-claim authority.

## 6. Supersession and change history

Compiled on 2026-08-31 from `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1` SHA-256 `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`. Pilot Candidate `764333bc...` is evidence only and is not imported as production code authority. On 2026-09-01, a corrective Owner handoff established that Pilot import mechanics did not prove production deployment topology; `OPEN_SWE_EXTERNAL_RUNTIME_CORRECTIVE_CONTRACT.md` supersedes in-process dependency/runtime instructions while preserving the historical Task Card records and settled Nexus authority boundaries. On 2026-09-03, `NEXUS_CONTROLLER_HANDOFF_V2` plus the Owner-authorized sanitized Ready reconciliation on Issue #695 froze H11 and activated TASK-005 on current-main `dc315c38562834923729dcb45bd2b85344c35bc9`. OpenCLI `1.8.7` is an explicit Owner-approved roadmap delta from unavailable npm `1.8.8`. A later explicit Owner decision on 2026-09-03 expanded TASK-005 to preserve pacing across Open SWE subprocess and runtime-restart boundaries using only hashed lock/state under the existing `runtime_state_root`; it forbids profile/session plaintext and any new queue/router authority. On 2026-09-08, bounded Web acceptance plus explicit Owner Issue #850 superseded TASK-005's activation assumptions with `balanced`/`ephemeral` and activated TASK-006 for resident five-repository integration.


## 7. r28 bounded closeout evidence

- Nexus-new base `a59b8ab23a91ae4470300a34b4691567255c12af`; runtime main `3eb673bfcfd874043a70743e34761784fda39c10`.
- Operation `96b83c02de43ff8e6bc37d49e0efabd3f113ac60135ea214c367094b24806574`; effect `effect_ef0802c64e2a8e8f8a65ccb696adf1b0d9d50b21a06348e10d931a038d88af68`.
- Unit Candidate `2d41308d27999f210627981a933f8f0da95e54f0`; Task Candidate `c5979ffbc664e019f6790bc5f6c84210749fa43c`; tree `a85cd07d4dc2d17f7551869565fcbc2fcf6512f3`.
- Task Card hash `d39a297583ebf37cdfbd0efa09a8c16f3ecf11ec7b9ced8a43dcc07d18d31fb1`; whole verification `512530748d61ea0537f5019956bbf07bbbec33a9e724a0790bdeb15cd47d3c6d` is `PASS`.
- Worker receipt `b893c704f2b8e2632d94c203f44a25a87f32dc9e9758ab5f9ac2d1ec0fb4d2b1`; five-mount receipt SHA `89d36c80399c15a4fe306c28318f4108d4b64cd90a1c94c643e8892bf4576f53`; final rollback/restore receipt SHA `1b7ce771a8b4aa14e94045a36b0a9aeeabcd9ed09b4a986ce1d87b1326907888`; closure capsule `ec02d8d07d681b88751ba20b7e1fbb8afdf1e103882554926fd5a4d6511a7694`; final READY run `0eb9a96de9f64454b21362a141a7d41a`.
- The original acceptance packet records `TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` / `PENDING_INDEPENDENT_ACCEPTANCE`; the later controller receipt `9638ef72801a31ca84560b8b7d3d99bd512925b593f7b535b993b762b5860cf6` independently accepts the Candidate for `CANDIDATE_ACCEPTED_FOR_R28_ACTIVATION_WITNESS`. `AUTO_CHAIN=false`; no merge, release, production, or all-repository mutation-readiness claim is made.
