# Live Online Recovery and Paired Pilot — 2026-07-14

## Campaign

`live_paired_20260713T2311Z` on branch `feature/repair-mainline-p0-20260708`.

## Starting Baseline

| Field | Value |
|---|---|
| Prior HEAD | `b106534a2` |
| LOCAL_ONLY | PROVEN (5× Ollama) |
| Prior Gemini Hybrid | IneligibleTierError (false discovery matrix later corrected) |

## Authorization Regression (R0)

**Defect A:** scenario `online_command` not classified as inject under workspace deny.

**Fix:** inject transport flags + inject-aware registered CLI guard; physical fail-closed preserved.

## Provider Discovery (R1) — corrected

Probe method: `Gateway.ask_structured` with bound OnlineExecutionDecision and **provider-specific CLI** (not always gemini).

| Provider | Status |
|---|---|
| grok | **READY** (output delivered) |
| agy | **READY** (output delivered) |
| gemini | **READY** via agy preference path / or probe |
| codex | PROVIDER_ERROR (model version mismatch) |
| openai | PROVIDER_ERROR |

**Selected:** `grok`

## Real Vertical Proof (R2)

| Field | Value |
|---|---|
| Seam | Gateway.ask_unified + UnifiedRuntime |
| Online policy | require |
| Local | ollama qwen2.5-coder:7b-instruct, invoked+delivered, calls≥1 |
| Online | grok, ONLINE_READY, invoked+delivered, gate passed |
| Context forward | true |
| Verifier | passed |
| receipt_complete | true |
| REAL_LOCAL_ONLINE_VERTICAL_PROVEN | **true** |

## Five Live Pairs (R3)

| Field | Value |
|---|---|
| Pairs | **5/5** complete |
| Provider | grok (same for all arms) |
| Arms | A disabled+require / B advisor+require |
| Order | alternating A/B |
| FIXTURE_MEASURED in live set | **false** |
| fixture_rows | 0 |

## Measurement Integrity (R4)

Live qualities: PROVIDER_REPORTED / LOCALLY_MEASURED / UNAVAILABLE (no FIXTURE_MEASURED).
Deltas recomputed; pair invariants enforced.

## Terminal States

```text
AUTHORIZATION_REGRESSION_STATUS = CLOSED
ONLINE_PROVIDER_READY_STATUS    = READY
LOCAL_ONLINE_VERTICAL_STATUS    = PROVEN
LIVE_PAIRED_PILOT_STATUS        = COMPLETE
VALUE_CLAIM_STATUS              = NOT_CLAIMED
NEXUS_LIVE_ONLINE_AND_PAIRED_PILOT_COMPLETE = true
```

## Claim Boundary

| Flag | Value |
|---|---|
| authorization_regression_closed | true |
| one_real_online_provider_ready | true |
| real_local_online_vertical_proven | true |
| five_task_live_measurement_pipeline_complete | true |
| proven_*_savings / production_ready / public_claim_allowed | **false** |

## Next Benchmark

Larger 30–50 task set; optional multi-repeat pairs; never auto-promote savings claims.
