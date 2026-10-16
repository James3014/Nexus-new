# Nexus R/Hyper P24 Hidden Verifier Failure Report

## Target

Confirm whether the P22 model-required Flash result can also satisfy the public claim gate with `NEXUS_VALUE_HIDDEN_VERIFIER=1`.

## Result

The run was intentionally stopped after the first failed Nexus row. This is not a valid public benchmark result.

Command:

```bash
NEXUS_CODEX_IGNORE_USER_CONFIG=1 NEXUS_VALUE_HIDDEN_VERIFIER=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --max-tasks 6 \
  --without-mode gemini \
  --with-llm-mode all \
  --with-model-provider gemini \
  --gemini-model gemini-3-flash-preview \
  --with-nexus-runner subprocess \
  --enable-llm-self-heal \
  --timeout-sec 240 \
  --per-task-stop-loss-sec 300 \
  --stop-loss-sec 2400 \
  --total-timeout-sec 2400 \
  --output-dir .nexus/reports/p24_flash_model_required_6task_hidden_verifier_no_shadow \
  --markdown-report auto
```

## Evidence

Partial row files were written under:

`.nexus/reports/p24_flash_model_required_6task_hidden_verifier_no_shadow/evidence_1778612446/`

Key rows:

- `model-required-feature-001`: `SUCCESS`, `model_uplift_eligible=True`, `nexus_winner_source=llm_self_heal`, `model_calls=2`, `wall=146.0103s`.
- `model-required-refactor-001`: `SUCCESS`, `model_uplift_eligible=True`, `nexus_winner_source=llm_self_heal`, `model_calls=2`, `wall=77.9408s`.
- `model-required-ops-001`: `SUCCESS`, `model_uplift_eligible=True`, `nexus_winner_source=llm`, `model_calls=1`, `wall=43.5385s`.
- `model-required-repair-001`: `SUCCESS`, but `model_uplift_eligible=False`, `nexus_winner_source=local`, `fallback_used=True`, `wall=175.9802s`.
- `model-required-docs-001`: `FAILED`, `infra_invalid_reason=nexus_delivery_invalid`, `timeout_scope=with_nexus_subprocess`, `timeout_stage=timeout_before_receipt`, `wall=240.036s`.

## Diagnosis

P24 found two separate issues:

1. Hidden verifier no longer forces all rows into `local_hidden_shadow`; the new `NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW=1` path worked for feature/refactor/ops rows.
2. Model-required + hidden-verifier still has a repair/docs failure mode:
   - repair can still end with generic `local` fallback after a model call;
   - docs can spend the whole subprocess timeout without returning a receipt.

This means the correct next fix is not another blind benchmark run. The next code change must make model-required execution fail closed when final delivery would be local, and it must return a structured timeout receipt before the subprocess wall is exhausted.

## Why This Stopped

This stop was intentional and evidence-driven: a model-required row failed before the full run completed. Continuing the remaining bare arm would have produced more cost without making the failure more diagnosable.

The previous repeated stop pattern came from treating phase labels as progress. This report records concrete row-level evidence and defines the next structural fix.
