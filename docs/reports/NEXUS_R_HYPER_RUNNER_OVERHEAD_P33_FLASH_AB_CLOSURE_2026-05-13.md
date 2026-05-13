# Nexus R/Hyper Runner Overhead P33 Flash A/B Closure

## Target

Make Gemini 3 Flash wearing Nexus produce verified delivery on a fixed public model-required repair task where bare Gemini 3 Flash fails, while preserving trust safety and honest cost evidence.

## Result

P33 met the minimum same-model evidence gate for `model-required-repair-001`.

| Arm | Verified | Eligible | Trust mismatch | Wall sec | Tokens | Clean cost evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemini 3 Flash + Nexus | 1/1 | 1/1 | 0.0 | 106.9617 | 61454 | 1.0 |
| Gemini 3 Flash bare | 0/1 | 1/1 | 0.0 | 29.1047 | 59067 | 1.0 |

Public claim gate: `PASS`.

Evidence bundle: `.nexus/reports/p33_flash_model_required_repair_ab/evidence_bundle.json`.

## Fixes Landed

- Model-required final delivery is fail-closed: local fallback may support diagnosis, but cannot become final delivery.
- Lite route now preserves bounded self-heal for `eligibility_class=model_required`.
- Model-required self-heal can use a local support candidate as a hint while keeping final delivery model-owned.
- Model-required fixture tests now add their own fixture directory to `sys.path`, preventing false verifier failures from `ModuleNotFoundError: No module named 'target'`.
- Gateway token stats now downgrade obvious cumulative stats outliers to estimated instead of reporting fake measured precision.

## Diagnosis

P28/P29/P30 were not all model-quality failures.

- P28 exposed a real policy defect: lite route suppressed bounded self-heal.
- P29 proved self-heal could be invoked, but failed.
- P30 revealed the hidden root cause: the generated model patch was correct, but the fixture verifier could not import `target` from `.nexus/bench_cases/...`.
- P31/P32/P33 verified that after fixing fixture import, Flash+Nexus passes the task.

## Remaining Cost Bottleneck

The remaining wall gap is not token cost.

- Token ratio with/bare: `1.0404x`.
- Wall ratio with/bare: `3.6751x`.
- R phase with Nexus: `39.8138s`.
- Runner/wrapper gap with Nexus: `56.4669s`, classed as `expected_wrapper_gap`.

Next optimization should target subprocess wrapper / hidden retry timing, not remove governance gates.

## Verification

```bash
uv run pytest tests/test_battlesuit_gateway.py tests/services/test_gemini_cli.py tests/benchmark/test_capability_ab_runner.py tests/research/test_sprint_service.py -q
# 261 passed in 17.81s
```

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 NEXUS_CODEX_IGNORE_USER_CONFIG=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --output-dir .nexus/reports/p33_flash_model_required_repair_ab \
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

Output artifacts:

- `.nexus/reports/p33_flash_model_required_repair_ab/with_nexus_1778617571.jsonl`
- `.nexus/reports/p33_flash_model_required_repair_ab/without_nexus_1778617571.jsonl`
- `.nexus/reports/p33_flash_model_required_repair_ab/gemini_nexus_report_1778617571.md`
- `.nexus/reports/p33_flash_model_required_repair_ab/evidence_bundle.json`

## Why Previous Runs Stopped

The loop kept stopping because each run exposed a different defect class, and earlier reports treated phase labels as progress:

- `model_required_local_delivery_blocked`: delivery eligibility seam, not model failure.
- `bounded_self_heal_not_triggered`: route-cost policy suppressed recovery.
- `self_heal_failed`: real invocation, but no sufficient diagnostic visibility.
- `ModuleNotFoundError: No module named 'target'`: fixture harness defect hidden inside R/hyper output.
- `stats_outlier_possible_cumulative`: cost evidence defect, not delivery defect.

The durable fix is to keep classifying failed rows before rerunning, and only mark a phase complete when code, tests, benchmark evidence, and learning writeback all exist.
