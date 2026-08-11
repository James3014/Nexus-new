---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: TC-P1A-G1
campaign_id: CAMPAIGN-PHASE1A-V1.1
source_issue: https://github.com/James3014/Nexus-new/issues/143
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
---

# Phase 1A G1 — arm/treatment identity and triplet comparability

## Objective

Implement the Owner-approved Issue #143 contract for explicit Phase 1A A/B/C arm identity and deterministic triplet comparability without changing legacy Epistemic Workflow `BenchmarkArm`, Verified Assist/VAP B/D semantics, or CapabilityPlanner route authority.

## Allowed mutation files

- `nexus/research/epistemic_benchmark/phase1a_contracts.py`
- `tests/test_phase1a_arm_contract.py`

All other repository files are read-only for this implementation Candidate.

## Worker binding

Owner-selected Candidate producer: Agy / `gemini-3.6-flash-medium` (`Gemini 3.6 Flash (Medium)`). This binding is execution guidance only; exact model output remains candidate-only and requires independent verification. Do not substitute `gemini-3.6-flash-high` or inherit any sibling-model evidence.

## Required behavior

Preserve the complete Issue #143 contract, including:

- A = Nexus baseline + Online + independent final verifier;
- B = deterministic evidence mediation + Online + independent final verifier;
- C = B + bounded Local semantic exploration + Online + independent final verifier;
- all arms require Online;
- A and B reject Phase 1A Local provider calls;
- C Local evidence never gains route, final-verifier, approval, or authoritative-result authority;
- deterministic triplet fingerprint binds task, task-contract, source/corpus, Online provider/model/prompt policy, tool surface, budgets/timeouts, final verifier, quality gate, and Planner decision identity;
- decision-bearing drift fails closed;
- legacy BenchmarkArm and VAP B/D labels/semantics cannot deserialize as Phase 1A A/B/C;
- no second Router/Planner/topology selector.

## Verification

Run exactly:

```bash
uv run pytest -q tests/test_phase1a_arm_contract.py
uv run ruff check nexus/research/epistemic_benchmark/phase1a_contracts.py tests/test_phase1a_arm_contract.py
uv run python -m compileall -q nexus/research/epistemic_benchmark/phase1a_contracts.py tests/test_phase1a_arm_contract.py
git diff --check
uv run pytest -q tests/research/test_epistemic_benchmark_contracts.py tests/services/test_verified_assist_contract.py
```

Also prove the two legacy reference files are unchanged from the bound base.

## Claim ceiling

Implementation output is Candidate-only: `phase1a_arm_and_triplet_identity_substrate_candidate_only`.

Independent acceptance of the exact Candidate is required before G2 may unlock. No self-acceptance, self-merge, #29 completion, formal G5 execution, model promotion, production claim, or public causal-benefit claim is authorized.
