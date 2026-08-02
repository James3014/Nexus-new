---
task_id: ERP-00-nexus-epistemic-profile-foundation
campaign_id: epistemic-research-profile-foundation
attempt_id: erp00-agy-gemini36-medium-a1
worker:
  provider: agy
  runtime_model_id: gemini-3.6-flash-medium
  role: owner-authorized-bounded-cross-module-implementer
  formal_workforce_status: not_promoted_by_this_task
implementation_status: candidate_ready
independent_acceptance: pending
---

# Task Card ERP-00: Nexus Epistemic Research Profile Foundation

## Objective
Establish the first version of the Epistemic Research Profile foundation inside Nexus (`/Users/jameschen/Workspace/nexus`), reusing existing Nexus Identity, ClaimBoundary, ClaimEvidenceReadModel, Receipt, Replay, Block, and Acceptance authority; while explicitly demoting `research-ledger/` as a nested experimental reference implementation.

## Baseline
- Nexus canonical root: `/Users/jameschen/Workspace/nexus` (branch: `nexus/integration/main`, HEAD: `ad130ac14399e0ee922c544e488dc4adfb87745b`)
- Research Ledger nested root: `/Users/jameschen/Workspace/nexus/research-ledger` (branch: `main`, HEAD: `d1fb495b437c0a6485c10ea1e26fd191d590124f`)

## Allowed Scope & Files
### Nexus Root
- Create:
  - `nexus/research/epistemic_profile/__init__.py`
  - `nexus/research/epistemic_profile/contracts.py`
  - `nexus/research/epistemic_profile/authority.py`
  - `nexus/research/epistemic_profile/adapter.py`
  - `tests/research/test_epistemic_profile_contracts.py`
  - `tests/research/test_epistemic_profile_authority.py`
  - `tests/research/test_epistemic_profile_adapter.py`
  - `docs/specs/NEXUS_EPISTEMIC_RESEARCH_PROFILE_V0.md`
- Modify:
  - `.gitignore`
  - `tasks/epistemic-research-profile-foundation/INDEX.md`
  - `tasks/epistemic-research-profile-foundation/00-nexus-epistemic-profile-foundation.md`

### Research Ledger Nested Root
- Modify / Create:
  - `research-ledger/README.md`
  - `research-ledger/NEXUS_PROFILE_BOUNDARY.md`

## Forbidden Scope
- No modification to `research-ledger/src/**` or `research-ledger/tests/**`.
- No modification to existing Nexus governance cores (`nexus/contracts/claim_evidence_read_model.py`, `nexus/evidence/claim_boundary.py`, `nexus/evidence/receipt_base.py`, `nexus/replay/**`, `nexus/engine/**`, `nexus/gate/**`, `nexus/lifecycle/**`, `nexus/governance/**`, etc.).
- No live runtime wiring, routing changes, or model workforce promotion.
- No push, merge, PR creation, or production readiness claims.

## Three Milestones
1. Milestone 0: Materialize owner-approved Task authority.
2. Milestone 1: Reconcile Research Ledger lab boundary.
3. Milestone 2: Implement Nexus Epistemic Research Profile foundation.

## Tests & Verification
- TDD required (RED evidence before production implementation).
- Mandatory Commands C1 - C9 must pass clean.
- Existing governance regression tests must remain 100% green.

## Commit Policy
- 3 independent candidate commits across 2 Git roots:
  1. Nexus root: `chore(tasks): activate epistemic profile foundation`
  2. Research Ledger root: `docs(research-ledger): define Nexus profile boundary`
  3. Nexus root: `feat(research): add epistemic profile foundation`

## Claim Ceiling & Independent Acceptance
- Maximum claim: Implementer-reported candidate readiness only.
- Independent acceptance required before any further integration or next task card creation.
