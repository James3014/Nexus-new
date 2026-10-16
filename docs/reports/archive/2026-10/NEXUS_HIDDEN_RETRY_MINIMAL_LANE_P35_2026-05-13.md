# Nexus Hidden Retry Minimal Lane P35

## Goal

Make hidden verifier retry route through a semantic lane instead of always using full `hyper_sprint`.

The accepted P35 gate is:

- narrow hidden verifier failures route to `minimal_patch`;
- broad governance/policy failures keep `full_hyper`;
- infra failures use `skipped_infra`;
- Flash+Nexus remains verified on the model-required repair diagnostic task;
- retry wall moves in the right direction versus P34 without removing delivery, claim, or artifact safety.

## Result

- Status: PARTIAL PASS.
- Classifier/lane wiring: PASS.
- Flash delivery: PASS.
- Trust mismatch: PASS (`0.0`).
- Cost efficiency: still `REGRESSED`.

The lane is now real: P35 row reports `hidden_retry_lane=minimal_patch` and `hidden_retry_classifier=narrow_assertion_failure`. The retry no longer records `r_phase_hyper_sprint_sec`; however, it still performs a second model call and remains expensive.

## P34 vs P35

| Metric | P34 Full Retry | P35 Minimal Lane |
|---|---:|---:|
| Flash+Nexus status | `VERIFIED` | `VERIFIED` |
| Flash bare status | `UNVERIFIED` | `UNVERIFIED` |
| Wall | `108.5705s` | `96.2356s` |
| Hidden retry wall | `50.2678s` | `47.9783s` |
| Hidden retry R wall | `38.8802s` | `36.2628s` |
| Hyper sprint retry wall | `38.8798s` | `0.0s` |
| Tokens | `122850` | `119908` |
| Model calls | `2` | `2` |
| Retry lane | missing/legacy | `minimal_patch` |
| Retry classifier | missing/legacy | `narrow_assertion_failure` |

## Code Change

- `scripts/bench/capability_ab_runner.py`
  - Added `HiddenRetryDecision`.
  - Added hidden failure classification.
  - Added `minimal_patch`, `full_hyper`, and `skipped_infra` lanes.
  - Narrow failures now retry with `--force-flow baseline` and `--candidate-count 1`.
  - Broad governance failures keep full hyper retry.
  - Infra failures record `hidden_retry_lane=skipped_infra` and do not retry.

- `tests/benchmark/test_capability_ab_runner.py`
  - Added classifier coverage for narrow, broad, compact, and infra failures.
  - Added integration coverage for minimal retry and skipped-infra telemetry.
  - Updated existing retry tests to assert semantic lane/classifier fields.

## Verification

```bash
uv run pytest \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_retry_classifier_selects_minimal_full_and_infra_lanes \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_compact_retry_keeps_candidate_cap \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_failure_retries_with_failure_evidence_when_self_heal_env_enabled \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_failure_retries_inprocess_with_failure_evidence \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_infra_failure_records_skipped_infra_lane \
  -q
```

Result: `5 passed in 0.74s`.

```bash
uv run pytest tests/benchmark/test_capability_ab_runner.py -q
```

Result: `195 passed in 4.25s`.

```bash
uv run pytest \
  tests/benchmark/test_capability_ab_runner.py \
  tests/research/test_sprint_service.py \
  tests/test_battlesuit_gateway.py \
  tests/services/test_gemini_cli.py \
  -q
```

Result: `264 passed in 17.87s`.

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 NEXUS_CODEX_IGNORE_USER_CONFIG=1 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --output-dir .nexus/reports/p35_flash_model_required_repair_minimal_hidden_retry \
  --task-id-filter model-required-repair-001 \
  --max-tasks 1 \
  --timeout-sec 210 \
  --per-task-stop-loss-sec 260 \
  --stop-loss-sec 520 \
  --total-timeout-sec 520 \
  --with-nexus-runner subprocess \
  --with-llm-mode hard \
  --with-model-provider gemini \
  --gemini-model gemini-3-flash-preview \
  --without-mode gemini \
  --force-learn-slo-ready \
  --neutralize-history \
  --materialize-missing \
  --enable-llm-self-heal \
  --evidence-bundle \
  --markdown-report auto
```

Result:

- `with_nexus`: `SUCCESS`, `VERIFIED`.
- `without_nexus`: `FAILED`, `UNVERIFIED`.
- Evidence bundle: `.nexus/reports/p35_flash_model_required_repair_minimal_hidden_retry/evidence_bundle.json`.
- Markdown report: `.nexus/reports/p35_flash_model_required_repair_minimal_hidden_retry/gemini_nexus_report_1778624540.md`.

## Diagnosis

The minimal lane is now connected, but cost efficiency remains regressed because the second model call still dominates. The lane removed the explicit `hyper_sprint` retry, but the baseline model call still consumes roughly the same order of wall/tokens.

Next structural target:

- reduce retry prompt/context payload;
- avoid re-sending the full Nexus task contract when the hidden failure is a narrow assertion;
- consider deterministic/local pre-retry before spending a second model call.

## Residual Debt

- P35 does not complete the final cost goal.
- It completes the classifier/lane prerequisite for the next cost-reduction slice.
- Cost efficiency remains `REGRESSED`, sample sufficient remains `false`.

