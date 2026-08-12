---
artifact_authority: current
owner: James Chen
status: ACTIVE
campaign_id: CAMPAIGN-PHASE1A-V1.1
source_issue: https://github.com/James3014/Nexus-new/issues/135
AUTO_CHAIN: false
---

# Phase 1A v1.1 implementation campaign

## Authority

Parent contract: Issue #135 (`PHASE_1A_EVIDENCE_MEDIATION_CONTRACT_REVALIDATED`).

Current campaign frontier: `PRE-FORMAL / BLOCKED_ON_#29`.

## Completed gates

- G1 / `TC-P1A-G1` / Issue #143: independently accepted and merged by PR #165; maximum claim `phase1a_arm_and_triplet_identity_substrate_implemented_and_verified`.
- G2 / `TC-P1A-G2` / Issue #166: independently accepted and merged by PR #168; accepted Candidate `c404202b893ab3e2234acced9480400bdc8dfa3d`, merge/current unlock fence `d1115ee1da8b8e7fac2fbac4ef659c3a4b5a1512`; maximum claim `phase1a_measurement_substrate_implemented_and_verified`.
- G3 / `TC-P1A-G3` / Issue #169: independently accepted and merged by PR #171; accepted Candidate `71cc9148c9dddc94f9153efc1d06e5dd73e906e2`, merge/current unlock fence `91c3e6aa6b0fa85f6fb91bef5853e83900834aea`; maximum claim `phase1a_qualification_freeze_substrate_implemented_and_verified`.
- G4 / `TC-P1A-G4` / Issue #172: independently accepted at Candidate `361938f907276e065892eb64ab059d0e0bf1e9cb` (tree `40bf6d1ae028335d04f08ab52f1bc51bcea1ada8`), merged by PR #181 as `ea8c15293455575b4312b92eeeebc69daa4abbcf`, and post-merge source readback succeeded; maximum claim `phase1a_report_replay_tamper_substrate_implemented_and_verified`.

Serial repository-substrate topology:

`G1 DONE -> G2 DONE -> G3 DONE -> G4 DONE -> PRE-FORMAL`

## Frontier

- PRE-FORMAL: `BLOCKED_ON_#29`.
- Issue #29 is open and currently classified `BLOCKED_EVIDENCE / KEEP OPEN`; no durable terminal evidence proves `ONLINE_LOCAL_SAME_TASK_CAUSAL_CONSUMPTION_VERIFIED`.
- The exact remaining semantic prerequisite is one fresh, independently accepted same-task chain: immutable Local/World-C evidence identity -> exact physical Online input/context consumption -> real Online provider call -> truthful contribution/receipt, with tamper/substitution negatives and current source/runtime/provider/Workforce bindings.
- Satisfying #29 does not itself authorize G5. The final PRE-FORMAL freeze must still rebind exact Online/Local provider+model+runtime identities, freeze meaningful-improvement thresholds before formal outcome inspection, freeze the formal corpus/task identities, and bind qualification readiness plus the current manifest/report-verifier identity.
- G5: absent / unauthorized. Do not create a G5 Issue, Task Card, or formal 15x3 execution from G1-G4 completion alone.

## Parallelism

- The serial G1-G4 implementation lane is complete; do not restart or duplicate it.
- Issue #29 is now the only hard prerequisite lane that can unblock Phase 1A PRE-FORMAL; final freeze/readiness conditions remain inside PRE-FORMAL itself.
- Adjacent World C Issues #90-#95 remain separate durable contracts and do not silently become new #29 hard prerequisites without fresh source evidence.
- Legacy #103 Epistemic Workflow semantics and Verified Assist/VAP B/D semantics remain regression boundaries, not downstream implementation dependencies.

## Coordination

There is no active Phase 1A G1-G4 implementation dispatch. Agy / `gemini-3.6-flash-medium` remains historical worker-binding context for the completed bounded Candidate lanes; it has no continuing mutation, approval, merge, route, verifier, runtime, release, or production authority from this campaign state.

Read-only #29/PRE-FORMAL analysis may proceed. Any future #29 live acceptance attempt must rebind fresh runtime/provider/Workforce identities under #29's own authority. Formal G5 remains outside the current authorized frontier.

## Claim ceiling

Current durable repository claim: `phase1a_g1_g4_preformal_substrate_implemented_and_verified`.

Explicit non-claims:
- #29 is not completed by implication;
- PRE-FORMAL is not satisfied while #29 remains `BLOCKED_EVIDENCE`;
- #29 completion alone would not authorize G5 without the remaining PRE-FORMAL freeze/readiness evidence;
- no qualification/formal Phase 1A experiment has been executed;
- no causal benefit is demonstrated;
- no Local Nexus runtime integration is claimed;
- no route/approval/release/production authority is transferred.
