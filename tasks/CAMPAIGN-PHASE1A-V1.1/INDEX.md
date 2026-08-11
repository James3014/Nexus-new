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

Current implementation frontier: `TC-P1A-G2` / Issue #166.

## Completed gate

- G1 / `TC-P1A-G1` / Issue #143: independently accepted and merged by PR #165.
- accepted Candidate: `50df61d250054851b5c07d1342cd740e54c41082`
- merge commit / current-main unlock fence: `2c2dfd45085c779419b86c729df93600bdefbbfb`
- maximum G1 claim: `phase1a_arm_and_triplet_identity_substrate_implemented_and_verified`.

## Frontier

- G2 / `TC-P1A-G2`: ACTIVE and Owner-approved for bounded Candidate implementation after this card is merged.
- G3: `SERIALIZE_AFTER` independent acceptance of the exact G2 Candidate.
- G4: transitively locked behind G3 acceptance.
- G5: absent / unauthorized; formal execution remains blocked by Issue #29 plus the pre-formal freeze gate.

## Parallelism

- Issue #29 remains `PARALLEL_NOW` relative to G2-G4.
- #29 does not block G2, G3, or G4; it joins the Phase 1A implementation lane only at the pre-formal gate before G5.
- Legacy #103 Epistemic Workflow semantics and Verified Assist/VAP B/D semantics remain regression boundaries, not downstream implementation dependencies.

## Coordination

Agy / `gemini-3.6-flash-medium` (`Gemini 3.6 Flash (Medium)`) is the Owner-selected bounded Candidate producer for G2. Model output is candidate-only and receives no approval, merge, route, verifier, runtime, release, or production authority. Sibling-model evidence does not transfer.

Codex and other workers must not create a competing G2 mutation while the active Agy dispatch exists. Read-only oversight and independent acceptance preparation are allowed.

## Claim ceiling

Until G2 independent acceptance and post-merge readback, the campaign may claim only that G1 is implemented/verified and G2 is the active bounded implementation frontier. No claim of qualification readiness, report replay readiness, #29 completion, formal experiment readiness, or causal benefit is authorized.
