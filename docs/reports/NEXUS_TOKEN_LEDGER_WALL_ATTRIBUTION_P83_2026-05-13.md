# Nexus P83 Token Ledger and Wall Attribution Report

Date: 2026-05-13

## Goal

Stabilize the evidence layer before the next cost-optimization slice:

- keep provider token measurement fail-closed;
- avoid treating cumulative provider stats as measured per-request tokens;
- expose direct Gemini/gateway wall-time buckets;
- keep public claim wording split between verified delivery and cost efficiency.

This slice does not claim the final cost target is complete.

## Context+ Diagnosis

The P82 evidence showed token ROI improving while wall time still regressed. The new P83 evidence narrows the issue:

- prompt/control overhead is not the dominant issue for this slice;
- provider token measurement now reaches 1.0 on the valid 2-task sample;
- wall regression remains localized to R/hyper / provider wait path;
- telemetry had an overlap risk because `gateway_total_sec` and phase wall may refer to overlapping spans.

## Acceptance Gate Result

Verdict: RETURN

Reason:

- delivery gate: PASS on the valid 2-task Flash sample;
- cost safety gate: PASS on the valid 2-task Flash sample;
- cost efficiency gate: REGRESSED;
- sample size: 2 valid pairs, below the configured 3-pair minimum for an efficiency claim;
- supplemental docs run is infra-invalid and must not be merged into public cost evidence.

## Evidence

Valid P83 run:

- evidence bundle: `.nexus/reports/p83_flash_token_ledger_wall_attribution_hidden_3task_1trial/evidence_bundle.json`
- markdown report: `.nexus/reports/p83_flash_token_ledger_wall_attribution_hidden_3task_1trial/gemini_nexus_report_1778651976.md`
- valid task pairs: 2
- with Nexus semantic verified rate: 1.0
- without Nexus semantic verified rate: 0.5
- trust mismatch rate: 0.0
- provider token measured rate with Nexus: 1.0
- provider token measured rate without Nexus: 1.0
- wall cost ratio with/without: 2.8408
- token cost ratio with/without: 1.0485
- avg gateway total sec with Nexus: 56.593
- avg R phase wall sec with Nexus: 154.4057
- cost efficiency: REGRESSED

Supplemental docs run:

- evidence bundle: `.nexus/reports/p83_flash_token_ledger_wall_attribution_hidden_docs_1trial/evidence_bundle.json`
- status: infra-invalid
- with Nexus invalid reason: `nexus_delivery_invalid`
- without Nexus invalid reason: `auth_failed`
- action: excluded from public evidence.

## Code Changes

- `nexus/services/gemini_cli.py`
  - prefers request-local `usageMetadata` over cumulative `stats`;
  - avoids adding `stats` and `usageMetadata` together.

- `nexus/services/gateway.py`
  - records gateway invocation build, process/provider wait, parse, and total timing;
  - adds token ledger status/source/raw/normalized fields for outlier accounting.

- `scripts/bench/capability_ab_runner.py`
  - records token ledger fields in rows;
  - records direct Gemini timing buckets;
  - adds gateway timing averages to evidence bundle;
  - caps `wall_attribution_known_share_with` at 1.0 and exposes `wall_attribution_known_share_uncapped_with` plus `wall_attribution_overlap_suspected`.

- `tests/services/test_gemini_cli.py`
  - verifies `usageMetadata` wins over cumulative `stats`.

- `tests/benchmark/test_capability_ab_runner.py`
  - verifies stats outlier normalization remains fail-closed;
  - verifies overlapping wall attribution is marked and capped.

- `.nexus/reports/learn/phase_writeback.jsonl`
  - writes back the test fixture mistake and invalid supplemental benchmark lesson.

## Verification

Targeted:

```bash
uv run pytest tests/services/test_gemini_cli.py \
  tests/benchmark/test_capability_ab_runner.py::test_direct_gemini_stats_outlier_keeps_provider_fail_closed_with_normalized_ledger \
  tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_cost_gate_when_nexus_cost_regresses_without_verified_lift \
  tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle \
  tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression \
  tests/benchmark/test_gemini_nexus_report.py::test_render_markdown_report_uses_split_claim_posture_from_evidence_bundle -q
```

Result: 10 passed.

Broader:

```bash
uv run pytest tests/services/test_gemini_cli.py \
  tests/benchmark/test_capability_ab_runner.py \
  tests/benchmark/test_gemini_nexus_report.py -q
```

Result: 239 passed.

Benchmark:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-repair-001,model-required-feature-001,model-required-docS-001 \
  --output-dir .nexus/reports/p83_flash_token_ledger_wall_attribution_hidden_3task_1trial \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --with-model-provider gemini \
  --without-mode gemini \
  --gemini-model gemini-3-flash-preview \
  --repeat-trials 1 \
  --timeout-sec 240 \
  --total-timeout-sec 900 \
  --stop-loss-sec 900 \
  --per-task-stop-loss-sec 300 \
  --neutralize-history \
  --evidence-bundle \
  --markdown-report auto
```

Result: 2 valid task pairs because `model-required-docS-001` was a typo. The typo was not counted as complete coverage.

Supplemental docs run:

```bash
.venv/bin/python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-docs-001 \
  --output-dir .nexus/reports/p83_flash_token_ledger_wall_attribution_hidden_docs_1trial \
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

Result: infra-invalid. Excluded from public evidence.

## Next Slice

P84 must target R/hyper wall directly. Provider token measurement is no longer the blocker on the valid sample.

