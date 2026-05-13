# Nexus Route Cost P66 Scope-Supervised Closure

Date: 2026-05-10

## Result

P66 closes the current Flash route-cost tuning loop for the 8-task RLM harder v2 public fixture set.

The accepted policy is not a global downgrade. It is lane-aware, contract-preserving slimming:

- Keep hardened Nexus path for governance guard where bare fails.
- Allow supervised bare-first only for feature scopes that have hidden-verifier evidence.
- Preserve provider token evidence for bounded Nexus rescue after a failed model attempt.
- Keep trust mismatch at zero and keep public gate fail-closed.

## Key Comparisons

| Run | Nexus verified | Bare verified | Trust mismatch | Provider token measured | Wall ratio | Median paired wall ratio | Token ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P63 scope supervised | 8/8 | 5/8 | 0.0 | 0.875 | 2.0238 | 1.9928 | 1.1498 |
| P64 provider preserve | 8/8 | 5/8 | 0.0 | 1.0 | 1.8035 | 1.1111 | 1.0201 |
| P66 memory supervised | 8/8 | 5/8 | 0.0 | 1.0 | 1.7990 | 0.9734 | 1.0257 |

## What Changed

### Provider token preservation for bounded rescue

Bounded Nexus rescue may succeed locally after a failed model attempt. Previously the rescue payload could overwrite token capture status with `not_applicable_local_only`, causing a row with real model-attempt tokens to lose provider token evidence.

P66 preserves first-attempt provider token telemetry into the rescue row:

- `model_total_tokens`
- `model_token_capture_status`
- `gateway_token_source`
- gateway usage/stat flags

This makes the row public-cost-evidence eligible when provider tokens were actually measured, while still preventing it from being counted as clean model-only cost.

### Scope-specific governance rule

The broad medium-risk governance supervised-bare rule was rejected because governance guard bare-first can add a failed model attempt before rescue.

The accepted rule is narrower:

- `feature:public-ops-research-governance-scope-medium-supervised`
- only `rlm_harder_v2_governance_scope`
- supervised bare-first with medium risk allowed
- hidden verifier remains the gate

### Memory contract supervised route

`rlm_harder_v2_memory_contract` repeatedly showed same-model bare sufficiency under hidden verifier, while the Nexus baseline path cost was high. P66 adds:

- `feature:rlm-memory-contract-medium-supervised`
- only `rlm_harder_v2_memory_contract`
- supervised bare-first with medium risk allowed
- escalate to Nexus on hidden-verifier failure

## P66 Evidence

Command:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=180 \
NEXUS_RLM_REPAIR_LOOP=1 \
NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=160 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_rlm_harder_v2.json \
  --output-dir .nexus/reports/flash_8x1_memory_supervised_p66 \
  --max-tasks 8 \
  --repeat-trials 1 \
  --timeout-sec 240 \
  --total-timeout-sec 3600 \
  --stop-loss-sec 3600 \
  --per-task-stop-loss-sec 420 \
  --difficulty all \
  --repo-kind-filter all \
  --force-flow auto \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --without-mode gemini \
  --strict-llm-baseline \
  --force-learn-slo-ready \
  --neutralize-history \
  --disable-learning-loop \
  --materialize-missing \
  --isolation-mode preserve_target \
  --evidence-bundle \
  --markdown-report auto \
  --progress-log
```

Evidence bundle:

- `.nexus/reports/flash_8x1_memory_supervised_p66/evidence_bundle.json`
- `.nexus/reports/flash_8x1_memory_supervised_p66/gemini_nexus_report_1778370711.md`

Gate checks:

```json
{
  "verdict": "PASS",
  "with_semantic_verified_rate": 1.0,
  "without_semantic_verified_rate": 0.625,
  "with_trust_mismatch_rate": 0.0,
  "wall_cost_ratio_with_over_without": 1.799,
  "median_paired_wall_cost_ratio_with_over_without": 0.9734,
  "token_cost_ratio_with_over_without": 1.0257,
  "provider_token_measured_rate_with": 1.0,
  "token_measured_rate_with": 1.0,
  "nexus_usage_valid_rate": 1.0
}
```

## Remaining Debt

- `rlm-harder-v2-governance-001` remains expensive because bare fails and Nexus baseline is required for verified delivery.
- `rlm-harder-v2-belief-001` still reports runner overhead pollution, but it now preserves provider token evidence correctly.
- This is a Flash 8x1 closure, not a multi-trial public launch claim by itself. Next public claim should use repeated same-model trials.
