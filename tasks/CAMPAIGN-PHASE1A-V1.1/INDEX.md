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

Current implementation frontier: `TC-P1A-G1` / Issue #143.

## Frontier

- G1 / `TC-P1A-G1`: ACTIVE and Owner-approved for bounded Candidate implementation.
- G2: locked until independent acceptance of the exact G1 Candidate.
- G3: transitively locked behind G2 acceptance.
- G4: transitively locked behind G3 acceptance.
- G5: absent / unauthorized; formal execution remains blocked by Issue #29 plus the pre-formal freeze gate.

## Coordination

Agy / Gemini 3.6 Flash Medium is the Owner-selected bounded Candidate producer for G1. Model output is candidate-only and receives no