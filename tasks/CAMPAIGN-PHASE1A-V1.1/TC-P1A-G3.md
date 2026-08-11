---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: TC-P1A-G3
campaign_id: CAMPAIGN-PHASE1A-V1.1
source_issue: https://github.com/James3014/Nexus-new/issues/169
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
---

# Phase 1A G3 — qualification harness, frozen manifest, invalid-run controls

## Objective

Implement Issue #169's Phase 1A qualification/freeze substrate without changing accepted G1/G2, legacy Epistemic Workflow manifest/report semantics, Verified Assist/VAP B/D semantics, CapabilityPlanner, or workforce authority.

## Source lineage

- parent contract: Issue #135 / `PHASE_1A_EVIDENCE_MEDIATION_CONTRACT_REVALIDATED`
- predecessor: Issue #166 / G2
- G2 accepted Candidate: `c404202b893ab3e2234acced9480400bdc8dfa3d`
- G2 merge / G3 unlock fence: `d1115ee1da8b8e7fac2fbac4ef659c3a4b5a1512`
- source groups: qualification isolation, frozen-manifest controls, deterministic six-permutation assignment, invalid-run taxonomy, pre-formal #29 gate.

## Allowed mutation files

- `nexus/research/epistemic_benchmark/phase1a_qualification.py`
- `tests/test_phase1a_qualification.py`

All other repository files are read-only for this Candidate.

## Worker binding

Owner-selected Candidate producer: Agy / `gemini-3.6-flash-medium` (`Gemini 3.6 Flash (Medium)`). Current Agy→Nexus structured-output wrapping is known unreliable. Do not substitute `gemini-3.6-flash-high`, inherit sibling-model evidence, or weaken permission/trust controls. Coordinator materialization under this frozen card is allowed when transport cannot return a usable Candidate; provenance must remain truthful.

## Required observable behavior

The exact Issue #169 contract is binding. Within the two-file scope implement:

1. qualification-vs-formal task identity separation and structural exclusion of qualification rows from formal effect analysis;
2. a deterministic frozen Phase 1A manifest binding every decision-bearing field enumerated in #169/#135;
3. explicit meaningful-improvement thresholds with no VAP B/D 15% default inheritance;
4. exact Online/Local provider+model identities and all policy/schema/contract identities;
5. deterministic six-permutation A/B/C assignment from task identity + seed with cohort counts differing by at most one;
6. closed `VALID_SUCCESS`, `VALID_FAILURE`, `INFRA_INVALID`, `TREATMENT_INVALID`, `INTEGRITY_INVALID` classification;
7. manifest/cohort incompatibility on any decision-bearing post-freeze drift;
8. a pre-formal readiness projection that cannot claim #29 satisfied or G5 authorized without exact external prerequisite evidence;
9. no route/model/provider selection authority, report verifier authority, approval authority, or experiment execution.

## Required negative evidence

Cover every Issue #169 negative, especially:
- qualification/formal overlap;
- missing required manifest identity;
- nested unordered decision-bearing input;
- mapping-order nondeterminism;
- implicit legacy 15% threshold;
- empty/implicit model/provider identities;
- missing explicit thresholds;
- post-freeze mutation treated as same cohort;
- nondeterministic/unbalanced permutation assignment;
- qualification rows entering formal-effect rows;
- infra/treatment/integrity invalid states mislabeled as semantic loss;
- #29 task label/boolean without exact external evidence treated as ready;
- manifest presence treated as G5 authorization.

## Read-only compatibility surfaces

Prove unchanged from the bound base:
- `nexus/research/epistemic_benchmark/phase1a_contracts.py`
- `nexus/research/epistemic_benchmark/phase1a_measurement.py`
- `nexus/research/epistemic_benchmark/contracts.py`
- `nexus/research/epistemic_benchmark/report.py`
- `nexus/services/verified_assist_contract.py`

## Verification

Run exactly:
```bash
uv run pytest -q tests/test_phase1a_qualification.py
uv run ruff check nexus/research/epistemic_benchmark/phase1a_qualification.py tests/test_phase1a_qualification.py
uv run ruff format --check --preview nexus/research/epistemic_benchmark/phase1a_qualification.py tests/test_phase1a_qualification.py
uv run python -m compileall -q nexus/research/epistemic_benchmark/phase1a_qualification.py tests/test_phase1a_qualification.py
git diff --check
uv run pytest -q tests/test_phase1a_arm_contract.py tests/test_phase1a_measurement.py tests/research/test_epistemic_benchmark_contracts.py tests/services/test_verified_assist_contract.py
```

## Candidate evidence

Bind exact base/head/tree, physical diff, changed-file inventory, exact verifier results, manifest determinism/tamper vectors, qualification-isolation vectors, permutation-balance evidence, invalid-run vectors, #29-not-satisfied witness, requirement/AC mapping, and unresolved deviations.

## Forbidden scope

- no edits outside the two allowed files;
- no G4 report replay/tamper implementation;
- no qualification/formal experiment execution;
- no #29 completion by implication;
- no G5 Issue/Card;
- no threshold tuning from formal outcomes;
- no model/workforce promotion;
- no production/public causal claim.

## Exit / next gate

Implementation output is Candidate-only: `phase1a_qualification_freeze_substrate_candidate_only`.

Independent acceptance of the exact Candidate is mandatory. Only after accepted merge + post-merge readback may G3 rise to `phase1a_qualification_freeze_substrate_implemented_and_verified` and G4 become the next frontier.
