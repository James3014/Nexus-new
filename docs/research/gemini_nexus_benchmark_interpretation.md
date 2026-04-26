# Gemini + Nexus Benchmark Interpretation

## Goal

Compare `Gemini bare` against `Gemini + Nexus` only after each row is eligible
for capability scoring. Infrastructure failures must not be counted as model or
Nexus solve failures.

## Eligibility Fields

Each benchmark row should include:

- `provider`
- `model_name`
- `run_eligible`
- `infra_invalid_reason`
- `invocation_started`
- `model_response_received`
- `model_calls`
- `total_tokens`
- `nexus_bootstrap_completed`

Allowed `infra_invalid_reason` values:

- `quota_exhausted`
- `auth_failed`
- `cli_missing`
- `timeout_before_model_call`
- `parse_error`
- `nexus_delivery_invalid`

Rows with `run_eligible=false` are reported in `infra_invalid_n` but excluded
from solve-rate, semantic-verified-rate, first-pass-rate, and trust-mismatch
denominators.

## Nexus-Wearing Evidence

For `Gemini + Nexus`, a row is eligible only when all are true:

- `model_calls > 0`
- `gemini_uses_nexus = true`
- `nexus_context_delivered = true`
- `nexus_pillars_observed` contains LanceDB, Memory, MemPalace, Belief, Artifact
- `nexus_phases_observed` contains P, X, D, R, A, C

If Gemini did not receive Nexus context, the row is marked
`infra_invalid_reason=nexus_delivery_invalid`. This prevents Nexus from being
credited for work Gemini did not perform while wearing Nexus.

## Report Metrics

Use eligible rows only for:

- `solve_rate`
- `semantic_verified_rate`
- `trust_mismatch_rate`
- `first_pass_rate`
- `avg_wall_time_sec`
- `avg_tokens`
- `avg_model_calls`

Always display:

- `total_n`
- `eligible_n`
- `infra_invalid_n`
- `infra_invalid_reasons`

## Run Order

1. Run a no-model dry-run to validate row schema and summary output.
2. When quota is available, run 3-task Gemini 3 Flash smoke.
3. Stop if `model_calls=0`, `nexus_context_delivered=false`, or any Nexus row is `nexus_delivery_invalid`.
4. Run 6 tasks, then 12 tasks only after smoke rows are eligible.
5. Keep Gemini 3 Flash and Gemini 3.1 Pro reports separate.
