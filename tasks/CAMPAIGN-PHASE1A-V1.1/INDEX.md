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

Current implementation frontier: `TC-P1A-G4` / Issue #172.

## Completed gates

- G1 / `TC-P1A-G1` / Issue #143: independently accepted and merged by PR #165; maximum claim `phase1a_arm_and_triplet_identity_substrate_implemented_and_verified`.
- G2 / `TC-P1A-G2` / Issue #166: independently accepted and merged by PR #168; accepted Candidate `c404202b893ab3e2234acced9480400bdc8dfa3d`, merge/current unlock fence `d1115ee1da8b8e7fac2fbac4ef659c3a4b5a1512`; maximum claim `phase1a_measurement_substrate_implemented_and_verified`.
- G3 / `TC-P1A-G3` / Issue #169: independently accepted and merged by PR #171; accepted Candidate `71cc9148c9dddc94f9153efc1d06e5dd73e906e2`, merge/current unlock fence `91c3e6aa6b0fa85f6fb91bef5853e83900834aea`; maximum claim `phase1a_qualification_freeze_substrate_implemented_and_verified`.

## Frontier

- G4 / `TC-P1A-G4` / Issue #172: ACTIVE and Owner-approved for bounded Candidate implementation after this card is merged.
- G5: absent / unauthorized; formal execution remains blocked by Issue #29 plus the final pre-formal freeze gate.

## Parallelism

- Issue #29 remains `PARALLEL_NOW` relative to G4.
- #29 does not block G4; it joins the Phase 1A serial implementation lane only at the pre-formal gate before G5.
- Legacy #103 Epistemic Workflow semantics and Verified Assist/VAP B/D semantics remain regression boundaries, not downstream implementation dependencies.

## Coordination

Agy / `gemini-3.6-flash-medium` (`Gemini 3.6 Flash (Medium)`) is the Owner-selected bounded Candidate producer for G4. The known Agy→Nexus structured-output wrapper defect does not authorize High substitution, sibling evidence transfer, or weaker permissions. Model output is candidate-only and receives no approval, merge, route, verifier, runtime, release, or production authority.

Codex and other workers must not create a competing G4 mutation while the active dispatch exists. Read-only oversight and independent acceptance preparation are allowed.

## Claim ceiling

G1/G2/G3 are implemented and independently verified; G4 is the active bounded implementation frontier. No report replay acceptance, #29 completion, formal experiment readiness, G5 authorization, or causal benefit is authorized.
