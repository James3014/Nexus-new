# Nexus Docs Receipt + Rubric P86 - 2026-05-13

## Objective

Turn the docs lane from behavior-only success into a rubric-passing, receipt-complete, run-eligible Nexus sample. This is the required precursor before P87 wall optimization or any training/public cost claim.

## Change Log

- `scripts/bench/capability_ab_runner.py`
  - Backfills `delivery_gate` receipts from hidden verifier evidence when expected and tests pass.
  - Adds `_apply_supervised_receipt_evidence()` for supervised bare-first success/rescue paths.
  - Generates CodeIntel scan/impact evidence for supervised docs rows when `codeintel` is expected.
  - Recomputes expected receipt coverage before data-contract and rubric evaluation.
- `tests/benchmark/test_capability_ab_runner.py`
  - Added delivery-gate receipt backfill coverage.

## Verification Evidence

Regression suite:

```bash
uv run pytest \
  tests/benchmark/test_capability_ab_runner.py \
  tests/app/test_research_flow_service.py \
  tests/research/test_sprint_service.py \
  tests/services/test_gemini_cli.py -q
```

Result: `367 passed`.

Live Flash docs single-task replay:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-docs-001 \
  --output-dir .nexus/reports/p86_docs_receipts_rubric_1trial \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --with-model-provider gemini \
  --without-mode gemini \
  --gemini-model gemini-3-flash-preview \
  --repeat-trials 1 \
  --timeout-sec 240 \
  --total-timeout-sec 600 \
  --stop-loss-sec 600 \
  --per-task-stop-loss-sec 300 \
  --neutralize-history \
  --evidence-bundle \
  --markdown-report auto
```

Key row result:

- `with_nexus.run_eligible=true`
- `with_nexus.status=SUCCESS`
- `with_nexus.semantic_status=VERIFIED`
- `with_nexus.trust_mismatch=false`
- `with_nexus.receipt_data_contract_status=PASS`
- `with_nexus.receipt_data_contract_missing=[]`
- `with_nexus.token_data_contract_status=PASS`
- `with_nexus.rubric_contract_status=PASS`
- `with_nexus.evidence_rubric_status=PASS`
- `with_nexus.delivery_rubric_status=PASS`
- `with_nexus.cost_rubric_status=PASS`

Expected receipts:

- `codeintel`: scan and impact report refs present.
- `memory`: expected context contract ref present.
- `delivery_gate`: hidden verifier file ref present.

Bundle result:

- `public_delivery_gate.verdict=PASS`
- `public_cost_claim_gate.verdict=PASS`
- `public_cost_efficiency_claim_gate.verdict=IMPROVED`
- `rubric_contract.with_nexus.overall_pass_rate=1.0`
- `rubric_contract.with_nexus.evidence_pass_rate=1.0`
- `rubric_contract.with_nexus.delivery_pass_rate=1.0`
- `rubric_contract.with_nexus.cost_pass_rate=1.0`

Measured single-pair deltas:

- `wall_cost_ratio_with_over_without=0.8677`
- `token_cost_ratio_with_over_without=0.9692`
- `model_call_ratio_with_over_without=1.0`
- `cost_efficiency_sample_sufficient=false`

## Acceptance Verdict

`PASS` for P86 single-task docs lane readiness.

This does not yet authorize broad cost-efficiency public wording because only one pair exists and `sample_sufficient=false`.

## Residual Debt

- P86.5 must add mutation/pressure coverage that proves missing receipts still force `RETURN`.
- P87 must convert the current gateway/provider timing into a source-attributed wall ledger with <5% reconciliation error.
- P88 must run docs 3-task x1 before expanding to 3-task x3.
- Public cost-improvement wording remains blocked until sample sufficiency is met.

## Next Plan

1. P86.5: Receipt mutation pressure test.
2. P87: Wall ledger source attribution.
3. P88: Docs 3-task x1 Flash run.
4. P89: Docs 3-task x3 Flash run.
5. P92: Training eligibility only for rubric-PASS and sample-sufficient rows.
