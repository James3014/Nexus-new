# ADR-2026-05-07: Always-On Auto Contract Exposed Baseline and Pro Lane Regressions

## Context

After closing the `forced-hyper` benchmark pollution, the same `3x1` tasks were rerun under:

- `--always-on-eval`
- `--force-flow auto`

This was the first valid always-on cost readout for:

- `gemini-3-flash-preview`
- `gemini-3.1-pro-preview`

## Findings

### Flash

- `with_nexus` stayed at `3/3` verified.
- `without_nexus` stayed at `2/3` verified.
- But `hidden` became more expensive than the prior forced-hyper run:
  - `strategy_path=baseline_only`
  - `phase R ~= 57.29s`
  - `total_tokens ~= 50.4k`

This means the main hidden-lane problem is no longer route misclassification. It is the baseline execution path inside `R`.

### Gemini 3.1 Pro

- `hidden` improved relative to the earlier forced-hyper run.
- `repair` still showed an extreme `R` cost spike:
  - `phase R ~= 147.66s`
- `governance` regressed:
  - `status=FAILED`
  - `semantic_status=UNVERIFIED`
  - `trust_mismatch=True`

This means the valid always-on contract revealed a real Pro-specific regression that had been masked by the earlier benchmark contract.

## Lesson

- Removing route pollution is necessary but not sufficient.
- Once the contract is valid, cost and trust regressions can move to:
  - `baseline_only` execution inside `R`
  - model-specific `hyper_direct_hard_skip_probe`
  - governance hardening behavior under the same lane

## Decision

Next optimization must target `Phase C/D`, not route:

- `Flash hidden`: slim `baseline_only` inside `R`
- `Pro repair`: slim `hyper_direct_hard_skip_probe` inside `R`
- `Pro governance`: investigate the trust regression before any further cost tuning
