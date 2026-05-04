# Nexus Public Benchmark Report (Flash + Pro) - 2026-05-03

## Benchmark setup
- Task set: `scripts/bench/public_benchmark_nexus_value_v1.json` (6 tasks)
- A/B rule: same model `with_nexus` vs `without_nexus`
- Hidden verifier: enabled (`NEXUS_VALUE_HIDDEN_VERIFIER=1`)

## Model results

### 1) `gemini-3-flash-preview`

| Lane | with_nexus solve | with_nexus semantic | with_nexus trust mismatch | with_nexus wall(s) | without_nexus solve | without_nexus semantic | without_nexus wall(s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full governance (`full_governance_opt_r1`) | 1.0000 | 1.0000 | 0.0000 | 66.2918 | 0.6667 | 0.6667 | 34.7840 |
| Lean governance (`lean_governance_opt_r1`) | 1.0000 | 1.0000 | 0.0000 | 42.8234 | 0.6000* | 0.6000* | 32.7457 |

\* `without_nexus eligible_n=5` (1 infra parse_error row excluded by eligibility rule).

### 2) `gemini-3.1-pro-preview`

| Lane | with_nexus solve | with_nexus semantic | with_nexus trust mismatch | with_nexus wall(s) | without_nexus solve | without_nexus semantic | without_nexus wall(s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full governance (`full_governance_opt_r2_fix`) | 1.0000 | 1.0000 | 0.0000 | 72.2629 | 0.3333 | 0.3333 | 19.8369 |
| Lean governance (`lean_governance_opt_r1`) | 1.0000 | 1.0000 | 0.0000 | 50.5510 | 0.3333 | 0.3333 | 15.5924 |

## What Nexus improved (same-model A/B)
- Flash:
  - Full lane solve uplift: `+33.33 pts` (0.6667 -> 1.0000)
  - Lean lane solve uplift: `+40.00 pts` (0.6000 -> 1.0000)
  - Semantic verified uplift mirrors solve uplift.
- Pro:
  - Full lane solve uplift: `+66.67 pts` (0.3333 -> 1.0000)
  - Lean lane solve uplift: `+66.67 pts` (0.3333 -> 1.0000)
  - Semantic verified uplift mirrors solve uplift.

## Governance decision
1. Default repeat-benchmark lane: **Lean governance** (best speed/quality tradeoff).
2. Public trust-max lane: **Full governance** (now recovered on Pro via `r2_fix`).

## Fixed rerun command block

```bash
# Flash lean lane
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=240 \
NEXUS_ULTRA_REUSE_WORKTREE=1 \
NEXUS_ULTRA_SKIP_GHOST_REGRESSION=1 \
uv run python scripts/bench/capability_ab_runner.py \
  --benchmark-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --mode compare \
  --with-nexus-runner subprocess \
  --without-mode bare \
  --with-nexus-lane lean_governance \
  --max-tasks 6 \
  --neutralize-history \
  --output-dir .nexus/reports/bench_flash_cost_opt_p6/lean_governance_opt_r1

# Pro full lane (fixed)
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3.1-pro-preview \
NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=420 \
NEXUS_ULTRA_REUSE_WORKTREE=1 \
uv run python scripts/bench/capability_ab_runner.py \
  --benchmark-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --mode compare \
  --with-nexus-runner subprocess \
  --without-mode bare \
  --with-nexus-lane full_governance \
  --max-tasks 6 \
  --neutralize-history \
  --output-dir .nexus/reports/bench_pro_cost_opt_p6/full_governance_opt_r2_fix
```

## Evidence paths
- Flash full: `.nexus/reports/bench_flash_cost_opt_p6/full_governance_opt_r1`
- Flash lean: `.nexus/reports/bench_flash_cost_opt_p6/lean_governance_opt_r1`
- Pro full fixed: `.nexus/reports/bench_pro_cost_opt_p6/full_governance_opt_r2_fix`
- Pro lean: `.nexus/reports/bench_pro_cost_opt_p6/lean_governance_opt_r1`
