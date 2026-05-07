# ADR-2026-05-07 Gemini Loop0 Same-Model Contract Lesson

## Context

During `Loop 0` setup, the initial Gemini benchmark preflight failed even though the command looked valid.

Failure reasons:

- `direct_model_env_missing`
- `autoreason_executor_flag_missing`
- `ddtree_executor_flag_missing`
- `llm_candidate_cap_below_ddtree_threshold`
- `ultra_review_dry_gate_flag_missing`

The practical risk was worse than a simple preflight failure:

- a run labeled as `flash` could silently fall back to `gemini-3.1-pro-preview`
- the benchmark would no longer be same-model bare vs same-model Nexus
- cost and solve conclusions would become invalid

## Decision

All public or internal weak-model always-on loop runs must explicitly lock the Gemini benchmark contract:

- set `NEXUS_DIRECT_GEMINI_MODEL=<same model>`
- set `--gemini-model <same model>`
- enable:
  - `--enable-autoreason-executor`
  - `--enable-ddtree-executor`
  - `--enable-ultra-review-dry-gate`
  - `--llm-candidate-cap 3`

## Consequence

This prevents two invalid states:

1. fake same-model comparison
2. public-model route benchmark without the intended capability stack

## Operational Rule

Before any `Loop 0`/`Loop 6` Gemini A/B run:

1. run `--preflight-only`
2. require:
   - `status=PASS`
   - `same_model=true`
   - `capability_readiness.status=PASS`
3. if any check fails, benchmark result is `HOLD`, not evidence
