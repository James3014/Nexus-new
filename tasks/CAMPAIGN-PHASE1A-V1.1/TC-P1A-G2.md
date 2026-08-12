---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: TC-P1A-G2
campaign_id: CAMPAIGN-PHASE1A-V1.1
source_issue: https://github.com/James3014/Nexus-new/issues/166
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
---

# Phase 1A G2 — EvidenceObservation, trajectory telemetry, recomputation metrics

## Objective

Implement the Owner-approved Issue #166 contract for Phase 1A measurement substrate without changing accepted G1 arm identity, legacy Epistemic Workflow observation/metric semantics, Verified Assist/VAP B/D semantics, or CapabilityPlanner route authority.

## Source lineage

- parent contract: Issue #135 / `PHASE_1A_EVIDENCE_MEDIATION_CONTRACT_REVALIDATED`
- predecessor: Issue #143 / G1
- G1 accepted Candidate: `50df61d250054851b5c07d1342cd740e54c41082`
- G1 merge / G2 unlock fence: `2c2dfd45085c779419b86c729df93600bdefbbfb`
- source groups: Phase 1A `EvidenceObservation`, trajectory telemetry, `RecomputationAvoided`, required metric families, and AC-P1A substrate criteria 3/5/6.

## Allowed mutation files

- `nexus/research/epistemic_benchmark/phase1a_measurement.py`
- `tests/test_phase1a_measurement.py`

All other repository files are read-only for this implementation Candidate.

## Worker binding

Owner-selected Candidate producer: Agy / `gemini-3.6-flash-medium` (`Gemini 3.6 Flash (Medium)`). This is Candidate-production guidance only and does not promote Medium into runtime workforce authority. Do not substitute `gemini-3.6-flash-high` and do not inherit sibling-model evidence.

## Required observable behavior

The exact Issue #166 contract is binding. The Candidate must provide, in the two-file scope:

1. a Phase-1A-scoped `EvidenceObservation` contract with deterministic identity, task/arm/producer-phase/epistemic-type/claim/evidence/source-hash/derivation/validation/verifier-independence bindings;
2. fail-closed OBSERVED vs INFERRED rules and an explicit ADMISSIBLE gate;
3. deterministic admissible-observation-set identity and a provider-safe handoff projection that cannot credit physical consumption by presence alone;
4. ordered identity-bound trajectory/action events covering the required phases/action kinds with exact/conservative signatures;
5. duplicate/non-monotonic and cross-task/arm/run trajectory drift rejection;
6. conservative multiset `RecomputationAvoided_BA` and `RecomputationAvoided_CB` exactly as frozen in #135/#166, including the anti-gaming rule that extra prework absent from baseline counts zero;
7. deterministic projection of all Issue #166 required metric families;
8. no weighted productivity score and no inheritance of the legacy VAP B/D 15% threshold;
9. no route, final-verifier, approval, correctness, runtime, worker-selection, or report authority.

## Required negative evidence

At minimum cover every explicit negative in Issue #166, including:

- OBSERVED without physical evidence/source hash;
- INFERRED without derivation lineage;
- ADMISSIBLE without validator evidence;
- forbidden truth/authority claims;
- non-admissible handoff;
- observation-set substitution/nondeterminism;
- nested unordered signature input;
- duplicate/non-monotonic sequence;
- trajectory identity drift;
- fuzzy signature as decision equality;
- incorrect multiset handling;
- extra-prework anti-gaming case;
- B-A and C-B formula regression;
- utilization without physical consumption identity;
- correct-target timing without frozen independent oracle;
- any telemetry/observation authority escalation.

## Read-only compatibility surfaces

Prove unchanged from the bound base:

- `nexus/research/epistemic_benchmark/phase1a_contracts.py`
- `nexus/research/epistemic_benchmark/observations.py`
- `nexus/research/epistemic_benchmark/metrics.py`
- `nexus/services/verified_assist_contract.py`

## Verification

Run exactly:

```bash
uv run pytest -q tests/test_phase1a_measurement.py
uv run ruff check nexus/research/epistemic_benchmark/phase1a_measurement.py tests/test_phase1a_measurement.py
uv run ruff format --check --preview nexus/research/epistemic_benchmark/phase1a_measurement.py tests/test_phase1a_measurement.py
uv run python -m compileall -q nexus/research/epistemic_benchmark/phase1a_measurement.py tests/test_phase1a_measurement.py
git diff --check
uv run pytest -q tests/test_phase1a_arm_contract.py tests/research/test_epistemic_benchmark_contracts.py tests/services/test_verified_assist_contract.py
```

## Candidate evidence

The PR must bind exact base/head/tree, physical diff, changed-file inventory, command results, positive/negative observation vectors, trajectory replay vectors, explicit B-A/C-B multiset witnesses, anti-gaming witness, utilization physical-consumption witness, and unresolved deviations.

## Forbidden scope

- no edits outside the two allowed files;
- no G3 qualification/frozen-manifest/invalid-run-final-policy implementation;
- no G4 report replay/tamper extension;
- no qualification or formal experiment execution;
- no #29 completion claim;
- no G5 Issue/Card;
- no model/workforce promotion;
- no production/public causal claim.

## Exit / next gate

Implementation output is Candidate-only: `phase1a_measurement_substrate_candidate_only`.

Independent acceptance of the exact Candidate is required. Only after accepted merge + post-merge readback may G2 rise to `phase1a_measurement_substrate_implemented_and_verified` and G3 become the next frontier.
