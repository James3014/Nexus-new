# ADR-2026-05-07: Always-On Benchmark Contract Must Not Force Hyper

## Context

`always-on Nexus` cost evaluation was being run with `--force-flow hyper_sprint`. That invalidates the product question, because hidden and bounded-repair lanes are supposed to auto-route into lighter paths when the route contract allows it.

## Failure

- Route slimming looked partially effective.
- Runtime rows still showed `strategy_path=hyper_direct_forced`.
- Phase-C analysis then over-attributed cost to the `R` phase, but the benchmark contract itself had already forced the heaviest `R` path.

## Lesson

- `always-on` evaluation and `forced-hyper` evaluation are different benchmark contracts.
- `always-on` must fail closed when:
  - `--force-flow != auto`
  - `--skip-llm-baseline` would implicitly bias the treatment arm into direct Hyper
  - `--llm-safe-probe` rewrites the contract into hard-only forced Hyper

## Decision

Add an explicit `--always-on-eval` guard in `scripts/bench/capability_ab_runner.py` so the benchmark runner rejects polluted contracts before generating misleading cost data.
