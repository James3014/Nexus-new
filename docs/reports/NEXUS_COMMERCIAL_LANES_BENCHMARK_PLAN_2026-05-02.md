# Nexus Commercial Lanes Benchmark Plan

## What

Commercial lanes split public benchmarking into three product questions:

1. `capability_lift`: does the same model solve more hard tasks when wearing Nexus?
2. `governed_delivery`: does Nexus turn output into verified, auditable delivery with low trust mismatch?
3. `cost_efficiency`: does Nexus choose the right amount of armor for each risk level?

The lane manifest is `scripts/bench/public_benchmark_commercial_lanes_v1.json`.

## Why

The three-model value report proves verified-delivery lift on the frozen Nexus value benchmark. It does not fully prove Swarm, Drone, Nightshift, Autoreason, DDTree, or Ultra Review as standalone product capabilities. Commercial lanes are the next public-safe layer: they test capability lift, governance, and cost separately so future claims do not overreach.

## How

Compile a lane into a runner task file:

```bash
uv run python scripts/bench/commercial_lane_tasks.py \
  --lane governed_delivery \
  --output /tmp/nexus_governed_delivery_tasks.json
```

Run the compiled lane with the same public benchmark rules:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=240 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file /tmp/nexus_governed_delivery_tasks.json \
  --public-disclosure-manifest .nexus/reports/sanitized_public_benchmark_nexus_value_v1.json \
  --output-dir .nexus/reports/bench_commercial_governed_delivery_gemini3flash_<tag> \
  --max-tasks 12 --repeat-trials 1 --timeout-sec 300 \
  --total-timeout-sec 7200 --stop-loss-sec 7200 --per-task-stop-loss-sec 600 \
  --difficulty all --repo-kind-filter neutral_fixture --force-flow auto \
  --with-nexus-runner subprocess --with-llm-mode hard --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --enable-autoreason-executor --enable-ddtree-executor --enable-ultra-review-dry-gate \
  --llm-candidate-cap 3 --enable-llm-self-heal \
  --evidence-bundle --markdown-report auto --progress-log
```

## Acceptance

- Every lane run must have `public_claim_gate.verdict == PASS`.
- Every lane run must include `route_cost_ledger.schema == nexus_route_cost_ledger_v1`.
- Every lane run must include `product_kpis.schema == nexus_product_kpis_v1`.
- Swarm / Drone / Nightshift public claims require the `governed_delivery` lane because the current three-model value report did not primarily exercise those capabilities.
- Regression comparison must use `docs/reports/NEXUS_PUBLIC_VALUE_REGRESSION_BASELINE_2026-05-02.json` before claiming routing improvement.

## Next Execution Order

1. Run `capability_lift` with Gemini 3 Flash as smoke.
2. Run `governed_delivery` with Gemini 3 Flash to validate Swarm / Drone / Nightshift claims.
3. Run `cost_efficiency` after routing cost tuning, because it is meant to catch over-armoring.
4. Only after all lanes pass, repeat with `gemini-3.1-pro-preview`.
