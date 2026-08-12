---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: TC-P1A-G4
campaign_id: CAMPAIGN-PHASE1A-V1.1
source_issue: https://github.com/James3014/Nexus-new/issues/172
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
---

# Phase 1A G4 — report replay, tamper verification, and negative controls

## Objective

Implement Issue #172's Phase 1A report/replay verifier substrate without changing accepted G1/G2/G3, legacy Epistemic Workflow report semantics, Verified Assist/VAP B/D semantics, CapabilityPlanner, workforce authority, Issue #29 evidence semantics, or G5 authorization.

## Source lineage

- parent contract: Issue #135 / `PHASE_1A_EVIDENCE_MEDIATION_CONTRACT_REVALIDATED`
- predecessor: Issue #169 / G3
- G3 accepted Candidate: `71cc9148c9dddc94f9153efc1d06e5dd73e906e2`
- G3 merge / G4 unlock fence: `91c3e6aa6b0fa85f6fb91bef5853e83900834aea`
- source groups: authoritative report source binding, deterministic replay, B-A/C-B mechanism recomputation, invalid-run exclusion, tamper/substitution/omission/reorder controls, bounded decision replay, report self-hash.

## Allowed mutation files

- `nexus/research/epistemic_benchmark/phase1a_report.py` — new file
- `tests/test_phase1a_report.py` — new file

All other repository files are read-only for this Candidate. If the Issue #172 contract cannot be satisfied in these two files with read-only imports/references, stop with `SCOPE_RECOMPILE_REQUIRED`; do not widen scope implicitly.

## Worker binding

Owner-selected Candidate producer: Agy / `gemini-3.6-flash-medium` (`Gemini 3.6 Flash (Medium)`). Do not substitute `gemini-3.6-flash-high`, inherit sibling-model evidence, or weaken permission/trust controls. Model output is Candidate-only and cannot self-accept or self-integrate.

## Required observable behavior

Within the two-file scope implement:

1. an explicitly Phase-1A-scoped authoritative report source binding that covers the frozen G3 manifest, complete A/B/C task-triplet and G1 treatment fingerprints, G2 trajectory/action-normalization identities, G2 observation/admissible-observation-set identities, provider-safe packet identity, physical-consumption proof identity, settlement/contribution identity, provider-call ledger identity, G3 valid/invalid classification identity, paired metric source identities, exact Online/Local provider+model identities, report schema/verifier identity, final bounded decision projection, and report self-hash;
2. deterministic rebuild/replay from authoritative bound source objects/identities rather than trusting stored metric totals or stored final decision text;
3. exact B-A and C-B mechanism projections from accepted G2 structures; C-A may be total-effect projection only and must not replace B-A/C-B mechanism contrasts;
4. G3 invalid-run exclusion so infra/treatment/integrity-invalid rows cannot enter semantic effect estimates as ordinary losses;
5. evidence-utilization binding through the existing Verified Assist physical-consumption authority only; do not create a second proof path;
6. exact frozen-manifest/cohort binding and incompatibility on manifest/version drift;
7. deterministic bounded decision replay using frozen rules/thresholds from #135/G3, without outcome-driven threshold tuning;
8. report self-hash covering every decision-bearing projection and failing closed on mutation;
9. verifier output that remains verification evidence only and cannot imply #29 completion, G5 authorization, route/approval/release authority, runtime integration, or causal benefit.

## Required tamper / negative evidence

Cover every Issue #172 negative, including:

- changed task identity;
- changed arm identity or B/C swap;
- Local provider call injected into B;
- Online call removed from any formal arm;
- source/action signature changed;
- trajectory event dropped, duplicated, or reordered where order is decision-bearing;
- evidence epistemic/admissibility type changed;
- admissible-observation-set identity substituted;
- provider-safe packet identity substituted;
- final prompt / physical-consumption proof substituted or tampered;
- settlement/contribution projection substituted;
- provider/model identity changed;
- scope/manifest identity changed;
- arm dropped or duplicated;
- invalid run inserted into semantic effect rows;
- stored metric total changed while raw source evidence is unchanged;
- frozen threshold changed;
- stored final decision altered;
- report self-hash altered;
- replay PASS treated as #29 completion, G5 authorization, route authority, approval, release, runtime integration, or causal proof.

## Read-only compatibility surfaces

Prove unchanged from the bound base:

- `nexus/research/epistemic_benchmark/report.py`
- `nexus/research/epistemic_benchmark/phase1a_contracts.py`
- `nexus/research/epistemic_benchmark/phase1a_measurement.py`
- `nexus/research/epistemic_benchmark/phase1a_qualification.py`
- `nexus/services/verified_assist_contract.py`

## Verification

Run exactly:

```bash
uv run pytest -q tests/test_phase1a_report.py
uv run ruff check nexus/research/epistemic_benchmark/phase1a_report.py tests/test_phase1a_report.py
uv run ruff format --check --preview nexus/research/epistemic_benchmark/phase1a_report.py tests/test_phase1a_report.py
uv run python -m compileall -q nexus/research/epistemic_benchmark/phase1a_report.py tests/test_phase1a_report.py
git diff --check
uv run pytest -q tests/test_phase1a_arm_contract.py tests/test_phase1a_measurement.py tests/test_phase1a_qualification.py tests/research/test_epistemic_benchmark_contracts.py tests/services/test_verified_assist_contract.py
```

## Candidate evidence

Bind exact base/head/tree, physical diff, changed-file inventory, exact verifier results, authoritative-source/replay vectors, all required tamper controls, B-A/C-B recomputation witness, invalid-run exclusion witness, self-hash witness, requirement/AC mapping, and unresolved deviations.

## Forbidden scope

- no edits outside the two allowed new files;
- no qualification/formal experiment execution;
- no Issue #29 completion by implication;
- no G5 Issue/Card or formal 15x3 runs;
- no threshold tuning from observed outcomes;
- no second physical-consumption verifier path;
- no route/model/provider/workforce/approval/release authority change;
- no runtime integration or production/public causal claim.

## Exit / next gate

Implementation output is Candidate-only: `phase1a_report_replay_tamper_substrate_candidate_only`.

Independent acceptance of the exact Candidate is mandatory. Only after accepted merge + post-merge readback may G4 rise to `phase1a_report_replay_tamper_substrate_implemented_and_verified`.

Even after G4 acceptance, formal Phase 1A remains blocked until Issue #29's exact same-task Local/World-C -> physical Online consumption -> truthful contribution evidence is independently satisfied and the final pre-formal freeze gate passes. G5 remains absent / unauthorized.
