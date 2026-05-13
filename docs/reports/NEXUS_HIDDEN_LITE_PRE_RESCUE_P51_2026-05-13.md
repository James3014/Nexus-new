# NEXUS Hidden-Lite Pre-Rescue P51

## Goal

Reduce Flash+Nexus R/hyper wall cost without removing Artifact/Claim/Delivery governance.

Closure gate:

- Keep same-model Flash+Nexus verified delivery above bare.
- Keep trust mismatch at 0.
- Remove hidden retry second model call for narrow assertion failures.
- Prevent hidden-lite model-required repair from entering full `hyper_sprint`.
- Measure cost on at least 3 paired samples before making efficiency wording.

## Changes

- Added hidden retry payload telemetry:
  - `hidden_retry_prompt_chars`
  - `hidden_retry_context_chars`
  - `hidden_retry_contract_chars`
  - `hidden_retry_tail_chars`
  - `hidden_retry_diff_chars`
  - `hidden_retry_prompt_budget`
- Added `minimal_v1` retry prompt budget for hidden verifier failures.
- Added deterministic hidden pre-retry for safe narrow assertion failures.
- Added hidden-lite baseline fast-path to keep compact model-required repair off `hyper_sprint`.
- Added deterministic failed-tests pre-rescue for hidden-lite baseline failures.
- Classified deterministic pre-rescue as `nexus_llm_deterministic_pre_rescue` so the model-required benchmark keeps honest model participation while recording Nexus local repair.

## Evidence

Local tests:

- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q`
  - `196 passed` after P47.
- `TMPDIR=/private/tmp TEMP=/private/tmp TMP=/private/tmp uv run pytest tests/benchmark/test_capability_ab_runner.py tests/research/test_sprint_service.py tests/test_battlesuit_gateway.py tests/services/test_gemini_cli.py -q`
  - `267 passed` after P49/P50.

Flash A/B evidence:

- P46: `.nexus/reports/p46_flash_model_required_repair_minimal_prompt_budget/evidence_bundle.json`
  - `hidden_retry_prompt_budget=minimal_v1`
  - `hidden_retry_prompt_chars=1651`
  - `hidden_retry_wall_sec=63.1689`
  - Result: telemetry worked, but second model call remained expensive.
- P47: `.nexus/reports/p47_flash_model_required_repair_deterministic_pre_retry/evidence_bundle.json`
  - `model_calls=1`
  - `hidden_retry_wall_sec=0.4149`
  - `total_tokens=59816`
  - Result: second model call removed; first-call `hyper_sprint` remained.
- P49: `.nexus/reports/p49_flash_model_required_repair_hidden_lite_pre_rescue/evidence_bundle.json`
  - `with_nexus wall=44.2122s`
  - `without_nexus wall=72.0136s`
  - `with_nexus tokens=58257`
  - `without_nexus tokens=66114`
  - Result: cost improved on this single pair, but delivery gate initially failed because source accounting was too local.
- P50: `.nexus/reports/p50_flash_model_required_repair_hidden_lite_claim_fixed/evidence_bundle.json`
  - `delivery PASS`
  - `cost_safety PASS`
  - `model_uplift_eligible=True`
  - `cost_efficiency REGRESSED`
  - Result: claim accounting fixed; single-pair provider wall regressed.
- P51: `.nexus/reports/p51_flash_model_required_repair_hidden_lite_3pair/evidence_bundle.json`
  - Flash+Nexus verified rate: `1.0`
  - Bare verified rate: `0.3333`
  - Trust mismatch: `0.0`
  - Model calls: `1.0` vs `1.0`
  - Hyper sprint wall: `0.0`
  - Median paired wall ratio: `1.3695`
  - Median paired token ratio: `1.1217`
  - Cost efficiency: `REGRESSED`

## Diagnosis

P34/P35 showed the original cost problem was hidden verifier retry causing a second model call.

P47 removed that second model call.

P48/P49 removed accidental full `hyper_sprint` from hidden-lite repair and added deterministic pre-rescue.

P51 shows the remaining cost issue is no longer retry or hyper. It is first model-call wall/token overhead under Nexus-wearing baseline:

- `gateway_total_chars=2061` is already small.
- `model_calls=1` matches bare.
- `hyper_sprint=0`.
- `hidden_retry=0`.
- Nexus still adds median wall/token overhead while improving verified delivery.

## Status

Goal is partially met:

- Verified delivery: met.
- Trust safety: met.
- Hidden retry second call removal: met.
- Hyper bypass for hidden-lite: met.
- Cost efficiency: not met.

Next structural target is supervised bare-first under Nexus governance: let the model use the same light prompt as bare, then let Nexus verify and apply deterministic governed rescue only when needed.

