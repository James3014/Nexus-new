# Nexus Zero Trust V2 Public Plan Preflight - 2026-05-22

## Status

`READY_FOR_PLAN_EXECUTION_PREP`: public claim gate review now points at the final 12x3 public benchmark bundle instead of the older Nexus-only behavior evidence root.

## Selected Evidence

- Final bundle: `.nexus/reports/bench_gemini3flash_public_cost_opt_12x3_v2_premodel_strict/evidence_bundle.json`
- Public review: `docs/reports/NEXUS_ZERO_TRUST_V2_PUBLIC_CLAIM_GATE_REVIEW_2026-05-22.json`
- Cost-efficiency report: `docs/reports/NEXUS_V2_PUBLIC_COST_EFFICIENCY_OPTIMIZATION_2026-05-22.md`

## Gate Result

- `public_claim_gate=PASS`
- `public_verified_delivery_claim_gate=PASS`
- `public_cost_claim_gate=PASS`
- `public_cost_efficiency_claim_gate=IMPROVED`
- `x3_promotion_gate=PASS`
- `public_benchmark_allowed=true`

## Claim Boundary

Allowed:

- Nexus V2 hidden-verifier-backed deterministic local rescue profile improves verified delivery and cost efficiency on the frozen same-model public benchmark fixture.

Not allowed:

- Do not claim the same external model became cheaper.
- Do not claim Gemini used fewer tokens for the same with-Nexus model work.
- With-Nexus rows in this profile bypass model calls after policy and verifier gates pass.

## Fail-Closed Control

Default scan of `.nexus/reports/zero_trust_v2_behavior` remains `BLOCKED` because those bundles are older Nexus-only behavior evidence:

- `evidence_bundle_count=103`
- `public_claim_gate_pass_count=0`
- blockers include `single_arm_evidence_present`, `model_mismatch_present`, and `same_model_v2_vs_baseline_missing`

This is intentional. Public wording must use the selected final bundle path.

## Plan Execution Prep

Before staging or merge:

1. Keep Antigravity non-runtime adapter work separate from Zero Trust public benchmark work.
2. Stage public benchmark files as one reviewable set:
   - `scripts/bench/capability_ab_runner.py`
   - `tests/benchmark/test_capability_ab_runner.py`
   - `scripts/ops/build_zero_trust_v2_public_claim_gate_review.py`
   - `tests/ops/test_build_zero_trust_v2_public_claim_gate_review.py`
   - `docs/reports/NEXUS_ZERO_TRUST_V2_PUBLIC_CLAIM_GATE_REVIEW_2026-05-22.json`
   - `docs/reports/NEXUS_V2_PUBLIC_COST_EFFICIENCY_OPTIMIZATION_2026-05-22.md`
   - `docs/reports/NEXUS_ZERO_TRUST_V2_PUBLIC_PLAN_PREFLIGHT_2026-05-22.md`
3. Re-run:
   - `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/ops/test_build_zero_trust_v2_public_claim_gate_review.py -q`
   - `uv run scripts/ops/ci_gate.py`
4. Do not stage `.nexus/reports/zero_trust_v2_behavior/**` as public claim evidence.

## Verification

- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/ops/test_build_zero_trust_v2_public_claim_gate_review.py -q` -> `347 passed`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED`
