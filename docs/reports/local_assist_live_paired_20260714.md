# Live Online Recovery and Paired Pilot — 2026-07-14

## Campaign

`live_paired_20260713T2311Z` on branch `feature/repair-mainline-p0-20260708`.

## Starting Baseline

| Field | Value |
|---|---|
| Prior HEAD | `b106534a2` |
| LOCAL_ONLY | PROVEN (5× Ollama) |
| Gemini Hybrid | IneligibleTierError / no Online delivery |

## Authorization Regression (R0)

**Defect A:** scenario harness did not classify deterministic `online_command` runners as `injected_transport`, so workspace `deny` failed closed Online and hybrid scenario stayed `INCOMPLETE`.

**Fix:**

- Scenario route marks explicit commands as inject (`selection_source=injected_transport`, `live_provider_claim=false`, `online_policy=auto`)
- Registered CLI guard allows inject-authorized decisions only; stamps non-live claim
- Gateway honors inject flags on `ask_unified`

Physical `guard_physical_online` remains fail-closed.

**Tests:** 219 collected / 219 passed (focused suite including scenarios).

## Provider Discovery (R1)

| Provider | Status |
|---|---|
| gemini | UNSUPPORTED_CLIENT |
| grok | UNAUTHENTICATED |
| codex | UNAUTHENTICATED |
| openai | UNAUTHENTICATED |

**Selected:** none (`ONLINE_PROVIDER_READY_STATUS = NONE_READY`)

## Real Vertical / Live Pairs (R2–R3)

Not executed as live proof. No READY provider. Manifests prepared under evidence `paired_manifest.json` for five families with arms A/B (`online_policy=require`). Zero live result rows (no fixture substitution).

## Measurement Integrity (R4)

Live set forbids `FIXTURE_MEASURED`. Offline recompute/contribution self-check recorded in `measurement_integrity.json`.

## Terminal States

```text
AUTHORIZATION_REGRESSION_STATUS = CLOSED
ONLINE_PROVIDER_READY_STATUS    = NONE_READY
LOCAL_ONLINE_VERTICAL_STATUS    = NOT_RUN_PROVIDER_AUTH_BLOCKED
LIVE_PAIRED_PILOT_STATUS        = NOT_RUN_PROVIDER_AUTH_BLOCKED
VALUE_CLAIM_STATUS              = NOT_CLAIMED
NEXUS_LIVE_ONLINE_AND_PAIRED_PILOT_COMPLETE = false
```

## Claim Boundary

| Flag | Value |
|---|---|
| authorization_regression_closed | true |
| one_real_online_provider_ready | false |
| real_local_online_vertical_proven | false |
| five_task_live_measurement_pipeline_complete | false |
| proven_*_savings / production_ready / public_claim_allowed | false |

## Next Benchmark

1. Restore Online auth (Gemini Antigravity migration or keys for grok/codex/openai).
2. Re-run discovery until one READY provider.
3. `nexus run … --online-policy require` vertical proof.
4. Five live A/B pairs with PROVIDER_REPORTED/LOCALLY_MEASURED only.
