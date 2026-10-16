# Nexus Rubric Contract P85.5 - 2026-05-13

## Objective

Make RubricEM-style stage rubrics a first-class benchmark contract for docs lane evidence hardening. The immediate goal is not cost improvement; it is preventing behavior-level success from being reported as public or training-eligible success when required Nexus receipts are missing.

## Change Log

- `scripts/bench/capability_ab_runner.py`
  - Added `nexus_rubric_contract_v1` on every annotated row.
  - Added stage rubrics: `plan_rubric`, `evidence_rubric`, `delivery_rubric`, `cost_rubric`.
  - Added bundle-level `nexus_rubric_contract_bundle_v1` summary.
  - Scoped capability receipt data contracts to the `with_nexus` arm only.
- `tests/benchmark/test_capability_ab_runner.py`
  - Added row-level rubric assertions for missing receipts and missing token telemetry.
  - Added bundle-level rubric summary coverage.

## Verification Evidence

Targeted tests:

```bash
uv run pytest \
  tests/benchmark/test_capability_ab_runner.py::test_extract_record_marks_missing_receipts_as_data_contract_violation \
  tests/benchmark/test_capability_ab_runner.py::test_extract_record_marks_model_call_without_tokens_as_data_contract_violation \
  tests/benchmark/test_capability_ab_runner.py::test_data_contract_violation_is_not_run_eligible \
  tests/benchmark/test_capability_ab_runner.py::test_evidence_bundle_reports_rubric_contract_summary -q
```

Result: `4 passed`.

Regression suite:

```bash
uv run pytest \
  tests/benchmark/test_capability_ab_runner.py \
  tests/app/test_research_flow_service.py \
  tests/research/test_sprint_service.py \
  tests/services/test_gemini_cli.py -q
```

Result: `366 passed`.

Live Flash docs single-task replay:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-docs-001 \
  --output-dir .nexus/reports/p85_5_rubric_contract_docs_1trial_b \
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

- `with_nexus.status=SUCCESS`
- `with_nexus.semantic_status=VERIFIED`
- `with_nexus.run_eligible=false`
- `with_nexus.infra_invalid_reason=receipt_data_contract_violation`
- `with_nexus.receipt_data_contract_missing=["codeintel","memory","delivery_gate"]`
- `with_nexus.token_data_contract_status=PASS`
- `with_nexus.rubric_contract_status=RETURN`
- `with_nexus.evidence_rubric_status=RETURN`
- `with_nexus.delivery_rubric_status=RETURN`
- `with_nexus.cost_rubric_status=PASS`

Bundle result:

- `public_delivery_gate.verdict=FAIL`
- `public_cost_claim_gate.verdict=FAIL`
- `public_claim_posture.allowed_public_wording=no_public_claim`
- `rubric_contract.with_nexus.evidence_pass_rate=0.0`
- `rubric_contract.with_nexus.cost_pass_rate=1.0`
- `rubric_contract.without_nexus.evidence_pass_rate=1.0`

## Acceptance Verdict

`RETURN`, intentionally.

The implementation of the rubric contract is working, but the docs lane itself is still missing required Nexus receipts. This means P85.5 is complete as a guardrail slice, while the larger objective remains blocked at P86 receipt generation.

## Residual Debt

- P86 must produce or merge real `codeintel`, `memory`, and `delivery_gate` receipts for the supervised bare-first / model-required docs path.
- P87 wall optimization must not proceed until docs lane has at least one `run_eligible=true` Nexus row with rubric PASS.
- Training export must treat current docs rows as observation-only.

## Next Plan

1. P86: Wire docs lane receipt generation for `codeintel`, `memory`, and `delivery_gate`.
2. P86.5: Add a receipt mutation/pressure test proving missing receipts force `RETURN`.
3. P87: Add source-attributed wall ledger only after P86 passes.
4. P88: Run docs 3-task x1 only after one docs row becomes run-eligible.
5. P92: Mark only rubric-PASS rows as `training_eligible`.
