# Local Assist Live Paired Pilot — 2026-07-14

## Campaign
`live_paired_20260713T2311Z` — Nexus Live Online Recovery and Five-Task Measured Paired Pilot (R0–R5).

## Terminal
`NEXUS_LIVE_ONLINE_AND_PAIRED_PILOT_COMPLETE = true`

| Field | Status |
|---|---|
| AUTHORIZATION_REGRESSION_STATUS | CLOSED |
| ONLINE_PROVIDER_READY_STATUS | READY (grok; also agy) |
| LOCAL_ONLINE_VERTICAL_STATUS | PROVEN via product `nexus run` |
| LIVE_PAIRED_PILOT_STATUS | COMPLETE (5/5 live pairs, no fixtures) |
| VALUE_CLAIM_STATUS | NOT_CLAIMED |

## Product vertical (R2)
- Entry: `scripts/engine/nexus_cli.py nexus run --local-assist-policy advisor --online-policy require`
- Local: ollama `qwen2.5-coder:7b-instruct`, invoked+delivered, call_count=1
- Online: grok registered print CLI via Gateway, invoked+delivered, call_count=1, gate passed
- Context forwarded with hashes; UR `receipt_complete=true`, terminal SUCCEEDED
- Formal workspace mutation: false
- Log: `SCRATCH/grok-goal-live-paired-r2cli/r2_vertical_nexus_run.log`
- Receipt: `.nexus/reports/local_assist_live_paired/live_paired_20260713T2311Z/vertical_receipt.json`

## Authorization fixes (R0)
- Injected scenario Online runners authorized as `injected_transport` without credentials
- Product path binds BattlesuitGateway when repairer lacks gateway
- `require` decision re-resolves when provider arrives after initial missing-provider seal
- UnifiedRuntime preserves product Local model pin over CapabilityPlanner bare `:7b` snapshot

## Provider discovery (R1)
- Selected: **grok** READY / ONLINE_READY / output delivered
- Blocked / weaker: gemini IneligibleTier / UNSUPPORTED_CLIENT historically; codex/openai PROVIDER_ERROR in earlier probes
- agy also READY in multi-provider CLI routing

## Five live pairs (R3–R4)
- 5 task families, arms A (disabled+require) / B (advisor+require)
- Provider: grok; measurement quality excludes FIXTURE_MEASURED
- Value claims (savings/quality) remain false — pilot sample only

## Tests
- Command recorded in `focused_tests.json`
- Collected 103, passed 103, failed 0
- HEAD at test capture: `24c362f7a3418f0b5f4733068591b05610088c24`

## Claim boundary
May be true: authorization closed, one Online provider ready, real Local+Online vertical proven, five-task live measurement pipeline complete.
Must remain false: proven_*_savings, production_ready, public_claim_allowed, generalized_market_value_proven.

## Evidence
- `.nexus/reports/local_assist_live_paired/live_paired_20260713T2311Z/`
- Mirror: `docs/reports/local_assist_live_paired_20260714_evidence/`
