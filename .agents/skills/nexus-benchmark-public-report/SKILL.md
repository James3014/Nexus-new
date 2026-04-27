---
name: nexus-benchmark-public-report
description: Use when running or interpreting public-candidate A/B benchmarks that compare the same model bare vs the same model wearing Nexus. Produces repeatable Gemini/Gemini+Nexus evidence with eligibility, hidden verifier, Nexus wearing, semantic verification, trust mismatch, wall time, token/model-call, and public-claim gate checks.
---

# Nexus Benchmark Public Report

## Use When

- The user asks how much Nexus improves Gemini or another model.
- A Nexus optimization needs before/after comparison.
- A report must support a public candidate claim.

## Required Framing

Nexus is the battlesuit, not the solving agent. The comparison must be:

- Same model bare.
- Same model wearing Nexus.
- Same task set.
- Same trials, timeouts, and hidden verifier setting.
- Same eligibility rules for both arms.

Never mix `gemini-3-flash-preview` and `gemini-3.1-pro-preview` in one headline claim.

## Preflight

1. Confirm model quota before running model benchmarks.
2. Confirm no long-running Gemini/benchmark subprocesses are already active.
3. Confirm worktree is clean or record the exact commit/diff.
4. Use hidden verifier for value claims:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1
```

5. Stop loss:

- Single task over 600s: stop and diagnose runner/gateway timeout first.
- Quota/auth/CLI failure: mark infra invalid, do not count as model ability failure.

## Smoke Command

Use 3-6 tasks before a full run.

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=300 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --output-dir .nexus/reports/bench_gemini3flash_smoke_<tag> \
  --max-tasks 6 --repeat-trials 1 --timeout-sec 420 \
  --total-timeout-sec 3600 --stop-loss-sec 3600 \
  --difficulty all --repo-kind-filter all --force-flow hyper_sprint \
  --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --evidence-bundle --markdown-report auto --progress-log
```

## Public Candidate Command

Run after smoke passes.

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=300 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --output-dir .nexus/reports/bench_gemini3flash_value12x2_<tag> \
  --max-tasks 12 --repeat-trials 2 --timeout-sec 420 \
  --total-timeout-sec 7200 --stop-loss-sec 7200 \
  --difficulty all --repo-kind-filter all --force-flow hyper_sprint \
  --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --evidence-bundle --markdown-report auto --progress-log
```

## Required Metrics

Report these for both arms:

- `model_name`
- `provider`
- `run_eligible`
- `infra_invalid_reason`
- `eligible_n`
- `infra_invalid_n`
- solve rate
- semantic verified rate
- trust mismatch rate
- average wall time
- token measured rate
- total/model tokens when public-safe
- model calls

For Nexus treatment also report:

- `gemini_uses_nexus`
- `nexus_context_delivered`
- five-pillar evidence
- six-phase completion
- claim verified
- self-heal/local rescue/guard fallback rates

## Public Claim Gate

Only make a public candidate claim when:

- `Public claim gate: PASS`
- `hidden_verifier_mode=true`
- same model in both arms
- `run_eligible` denominator excludes infra-invalid rows in both arms
- trust mismatch is 0 or explicitly explained
- raw JSONL, evidence bundle, command, and model name are preserved

Allowed claim shape:

```text
On a frozen <N>-task benchmark with <T> trials per task, using <same model>,
Gemini + Nexus changed verified delivery from <bare>% to <nexus>%,
changed average wall time by <x>%, changed measured tokens by <y>%,
and preserved trust mismatch at <z>%. Nexus wearing evidence was valid for <n>/<n> treatment rows.
```

## Failure Handling

- If both arms are identical, the benchmark may be too easy; create harder hidden-verifier tasks before claiming no value.
- If Nexus is slower but more successful, report both the lift and the cost.
- If bare has quota/auth/CLI failure, label infra invalid and rerun later before making product claims.
- If Nexus rows lack wearing evidence, the run is invalid for battlesuit claims.
