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
repair_attempt:
  attempt_id: erp00-agy-gemini36-medium-a2
  status: authorized
  source_rejection: ERP-00 independent acceptance A1
  independent_acceptance: pending
repair_attempt_a3:
  attempt_id: erp00-agy-gemini36-medium-a3
  status: authorized
  source_rejection: ERP-00 independent acceptance A2
  repair_class: pre_existing_contract_mismatch
  independent_acceptance: pending
ratification_attempt_a4:
  attempt_id: erp00-agy-gemini36-medium-a4
  status: owner_authorized
  purpose: exact_a3_scope_and_lineage_ratification
  source_candidate_sha: 0980f19fff24697e2f30fd90c0027b00fda03bde
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

## Owner-authorized Repair Attempt A2
- **Attempt ID**: `erp00-agy-gemini36-medium-a2`
- **Scope of Repair**:
  1. Revert `nexus/research/contamination_guard.py` modification back to base `ad130ac14399e0ee922c544e488dc4adfb87745b` behavior.
  2. Enforce fail-closed validation on all authority and permission fields in `EpistemicAuthorityBoundary`.
  3. Enforce fail-closed validation on claim ID binding, artifact relative ref binding, and closed-set completion status across verification result and direct read-model builders.
- **Allowed Paths for A2**:
  - `tasks/epistemic-research-profile-foundation/00-nexus-epistemic-profile-foundation.md`
  - `nexus/research/contamination_guard.py`
  - `nexus/research/epistemic_profile/authority.py`
  - `nexus/research/epistemic_profile/contracts.py`
  - `nexus/research/epistemic_profile/adapter.py`
  - `tests/research/test_epistemic_profile_authority.py`
  - `tests/research/test_epistemic_profile_contracts.py`
  - `tests/research/test_epistemic_profile_adapter.py`
- **Prohibitions**: No ERP-01, no runtime wiring, no routing changes, no integration, no merge, no push, no public claim.
- **Output**: Candidate commit only for independent acceptance.

## Owner-authorized Repair Attempt A3

- Restore field-level contamination detection required by the existing
  `test_research_isolation.py` contract.
- The repair may reuse `has_design_fields()` from
  `nexus.research.research_facts`.
- The exact A3 paths are recorded in the owner-authorized A4 ratification section below.
- No Epistemic Profile contract, adapter, authority, runtime, routing,
  acceptance, integration, push, ERP-01, or public-claim changes are authorized.
- Output remains an implementer Candidate pending independent acceptance.

## Owner-authorized A3 Candidate Ratification — A4

### Reason

The A3 execution packet restricted mutation to three exact paths, but the
Git-tracked Task Card did not enumerate those paths. The owner now explicitly
adopts and ratifies the exact immutable A3 Candidate identified below.

This ratification does not claim that the original A3 mutation had complete
pre-mutation Git authority. It creates a new owner-authorized lineage closure
for the current exact physical Candidate and does not rewrite prior history.

### Ratified Candidate Identity

- Base SHA:
  `b4b52ffd94b30549f77aac64719efb1539050082`
- A3 authority commit:
  `a3edf0b2c24d6ccc449468f48440e77e2dfa84e8`
- A3 repair commit / Candidate SHA:
  `0980f19fff24697e2f30fd90c0027b00fda03bde`
- A3 full diff SHA-256:
  `141694d5c5bd9a22688a2e57c1c30ebe1d438f6b997ac201e08f36d99f5038d4`
- A3 behavioral diff SHA-256:
  `ab37505818fc95fc01d3889c0817fdff3e608e65998d0271cde62e004b5fe1f0`

### Exact Ratified A3 Paths

The owner ratifies only the following A3 paths:

1. `tasks/epistemic-research-profile-foundation/00-nexus-epistemic-profile-foundation.md`
2. `nexus/research/contamination_guard.py`
3. `tests/research/test_research_isolation.py`

No other path is included or implicitly authorized.

### Ratified Behavioral Scope

The adopted A3 behavior is limited to:

- Reusing `has_design_fields()` from
  `nexus.research.research_facts`.
- Detecting top-level prohibited design fields as `design_field`.
- Preserving existing text-term contamination detection.
- Preserving order while removing duplicate detected signals.
- Adding a field-only regression test using
  `patch_plan: candidate_001`.

The ratification does not authorize recursive field scanning, modification of
`DESIGN_TERMS`, changes to Epistemic Profile contracts, runtime wiring,
routing, workforce changes, acceptance authority, integration, push, public
claims, production claims, or ERP-01.

### A4 Scope

A4 may modify only this Task Card. A4 must not modify production code, tests,
specifications, campaign index, nested Research Ledger, runtime state, or
governance cores.

A4 output is an authority/lineage Candidate only. Independent acceptance is
still required.

## Tests & Verification
- TDD required (RED evidence before production implementation).
- Mandatory Commands C1 - C10 must pass clean.
- Existing governance regression tests must remain 100% green.

## Commit Policy
- Candidate commit for independent acceptance review.

## Claim Ceiling & Independent Acceptance
- Maximum claim: Implementer-reported candidate readiness only.
- Independent acceptance required before any further integration or next task card creation.
