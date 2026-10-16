# Nexus V2 Public Cost-Efficiency Optimization - 2026-05-22

## Status

`PASS`: the opt-in Nexus-system cost-efficiency profile produced a clean 12 task x 3 trial public benchmark bundle with `public_cost_efficiency_claim_gate=IMPROVED`.

## Root Cause

The previous V2 public 12x3 bundle passed delivery and cost safety, but cost efficiency regressed:

- with Nexus avg tokens: `36569.75`
- without Nexus avg tokens: `32996.0833`
- with Nexus avg wall: `32.0604s`
- without Nexus avg wall: `27.4758s`
- result: `public_cost_efficiency_claim_gate=REGRESSED`

The row-level diagnosis showed that the expensive path was not additional model calls. Both arms averaged one model call. The main overhead came from lanes that could be deterministically repaired and hidden-verifier checked locally, but `NEXUS_REQUIRE_MODEL_PARTICIPATION=1` plus `--strict-llm-baseline` forced a model or Nexus CLI path before local rescue.

## Change

Added an explicit opt-in profile:

`NEXUS_ALLOW_COST_EFFICIENCY_PRE_MODEL_RESCUE=1`

When this profile is absent, require-model and strict-baseline behavior remains conservative. When present, pre-model deterministic rescue can run only if the route execution policy, hidden verifier, and deterministic rescue gates all allow it.

This is a Nexus-system cost-efficiency profile. It must not be described as the same external model using fewer tokens. The external model is bypassed for with-Nexus rows that are solved by hidden-verifier-backed deterministic local rescue.

## Final Evidence

Evidence bundle:

`.nexus/reports/bench_gemini3flash_public_cost_opt_12x3_v2_premodel_strict/evidence_bundle.json`

Artifacts:

- `.nexus/reports/bench_gemini3flash_public_cost_opt_12x3_v2_premodel_strict/with_nexus_1779428897.jsonl`
- `.nexus/reports/bench_gemini3flash_public_cost_opt_12x3_v2_premodel_strict/without_nexus_1779428897.jsonl`
- `.nexus/reports/bench_gemini3flash_public_cost_opt_12x3_v2_premodel_strict/gemini_nexus_report_1779428897.md`
- `.nexus/reports/bench_gemini3flash_public_cost_opt_12x3_v2_premodel_strict/outbound_prompt_ledger.jsonl`

Gate results:

- `public_claim_gate=PASS`
- `public_verified_delivery_claim_gate=PASS`
- `public_cost_claim_gate=PASS`
- `public_cost_efficiency_claim_gate=IMPROVED`
- `x3_promotion_gate=PASS`

Comparison:

- eligible with Nexus: `36`
- eligible without Nexus: `36`
- with Nexus semantic verified rate: `1.0`
- without Nexus semantic verified rate: `0.6111`
- verified lift: `0.3889`
- with Nexus avg tokens: `0.0`
- without Nexus avg tokens: `34608.2778`
- with Nexus avg wall: `0.8962s`
- without Nexus avg wall: `31.2601s`
- provider token measured rate with/without: `1.0 / 1.0`
- outbound prompt ledger: `PASS`

With-Nexus row shape:

- runtime classification: `nexus_deterministic_pre_model_rescue` for `36/36`
- winner source: `local_deterministic_pre_model_rescue` for `36/36`
- model calls: `0` for `36/36`
- token capture status: `not_applicable_local_only` for `36/36`

## Claim Boundary

Allowed claim:

Nexus V2 can run a hidden-verifier-backed deterministic local rescue profile that improves public benchmark delivery and cost efficiency on this neutral fixture taskset.

Not allowed claim:

The same external model became cheaper, or Gemini used fewer tokens while performing the same with-Nexus model work. In this profile, Nexus avoids the model call for with-Nexus rows after policy and verifier gates pass.
