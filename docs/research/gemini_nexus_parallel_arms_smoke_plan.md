# Gemini + Nexus Parallel Arms Smoke Plan

## What

`--parallel-arms smoke-only` is a benchmark runner wiring check. It creates paired bare/Nexus rows with the same task/trial matrix, but it does not invoke Gemini, Nexus, pytest, or target mutation.

## Why

True parallel bare-vs-Nexus execution would currently race on shared fixture target files and shared local runtime resources. Smoke-only mode lets us validate output contracts and report guardrails without creating misleading public performance data.

## How

- Synthetic rows are marked `parallel_arms_mode=smoke-only`.
- Rows are `run_eligible=false` with `infra_invalid_reason=parallel_smoke`.
- Evidence bundle and markdown public claim gates must fail with `parallel_smoke`.
- Public solve-rate, token, wall-time, or Nexus-lift claims are forbidden from smoke-only runs.
- Formal public candidate runs remain sequential until each arm has isolated worktrees or copied fixtures.
