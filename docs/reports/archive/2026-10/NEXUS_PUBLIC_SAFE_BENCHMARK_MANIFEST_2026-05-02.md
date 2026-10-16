# Nexus Public-Safe Benchmark Manifest Fix - 2026-05-02

## What

External model benchmarks must use a public-safe payload pair:

1. execution-safe tasks file for the runner
2. disclosure manifest for preflight and report trust

Use `scripts/bench/commercial_lane_tasks.py` as the single lane compiler:

```bash
uv run python scripts/bench/commercial_lane_tasks.py \
  --lane cost_efficiency \
  --output .nexus/reports/public_benchmark_manifests/cost_efficiency.runner.json \
  --execution-safe-output .nexus/reports/public_benchmark_manifests/cost_efficiency.execution_safe.json \
  --disclosure-output .nexus/reports/public_benchmark_manifests/cost_efficiency.disclosure.json
```

Run Gemini/other external model benchmarks against the `*.execution_safe.json` file and pass the matching `*.disclosure.json` file to `--public-disclosure-manifest`.

## Why

Repeated benchmark stalls happened because ad hoc `/tmp/*tasks.json` files looked like local benchmark/task/code context. User approval cannot convert a local workspace payload into a public disclosure artifact. The stable fix is to stop sending ad hoc local task files and always compile a sanitized public fixture manifest first.

## How

`commercial_lane_tasks.py` now emits three artifacts:

- `runner.json`: internal compiled lane task list
- `execution_safe.json`: external-runner-safe task list with fixture-only repo references and generic public file scope
- `disclosure.json`: public disclosure manifest with local file scope removed

The disclosure manifest is checked by `capability_ab_runner.py --preflight-only`; it must pass before any external model run.

Verified cost-efficiency preflight:

- tasks loaded: 6
- disclosure status: PASS
- model lock: `gemini-3-flash-preview == gemini-3-flash-preview`
- capability readiness: PASS
- report: `.nexus/reports/bench/benchmark_preflight.json`

Residual warning:

- cost-efficiency lane intentionally covers cost/routing capabilities, not all 16 core capabilities. Full capability coverage belongs to the `capability_lift` and `governed_delivery` lanes.
