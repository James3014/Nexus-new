# Real Hybrid Pilot — 2026-07-14

## Campaign

Nexus real Local-only + Local+Online vertical attempt + five-task paired measurement pipeline.

Campaign id: `real_hybrid_pilot_20260713T2204Z`

## Starting Baseline

| Field | Value |
|---|---|
| Branch | `feature/repair-mainline-p0-20260708` |
| Start HEAD (goal note) | `86104ef6b…` |
| Evidence binding HEAD | recorded in campaign `baseline_git.json` / closeout |

## Schema Repair (P0-A)

- Operator fixture keeps schema `nexus.local_assist.live_smoke_task.v1`.
- Explicit translator: `nexus.services.local_assist_live_smoke.translate_live_smoke_to_request`.
- `LocalAssistRequest.from_dict` still rejects foreign schemas on `validate()`.
- Loader/CLI path: `load_request_file` + `run_local_assist_command` translate live-smoke explicitly.
- Integration tests: `tests/services/test_local_assist_live_smoke.py`.

## Local-Only Real Proof (P0-B)

| Metric | Result |
|---|---|
| Tasks | 5/5 SUCCEEDED |
| Provider | ollama |
| Model | qwen2.5-coder:7b-instruct |
| Injected | no |
| formal_workspace_mutated | false |

Evidence: `.nexus/reports/local_assist_real_pilot/real_hybrid_pilot_20260713T2204Z/local_only_results.jsonl`

Task families: target-id, failure diagnosis, cross-file, regression risk, no-change.

## Local+Online Vertical Proof (P0-C)

| Step | Result |
|---|---|
| `nexus run … --local-assist-policy advisor --online-policy auto` | entered Master Loop; composition short-circuit (no UR receipt on that path) |
| Canonical seam UnifiedRuntime + LocalAssist + Gateway | Local SUCCEEDED (ollama) |
| Online preflight | `ONLINE_READY` (cli_task_policy auto, physical allowed) |
| Online physical gemini CLI | **auth blocked**: `IneligibleTierError` (Gemini Code Assist tier / migration) |
| Other providers | no XAI/GROK/OPENAI keys in env |

**LOCAL_ONLINE_LIVE_STATUS** = `IMPLEMENTED_NOT_LIVE_PROVEN_ONLINE_AUTH_BLOCKED`

Evidence: `vertical_proof_receipt.json`, `vertical_ur_receipt.json`, `vertical_pipeline_report.json`

## Measurement Integrity (P0-D)

Provenance enum:

- FIXTURE_MEASURED / PROVIDER_REPORTED / LOCALLY_MEASURED / ESTIMATED / UNAVAILABLE / NOT_APPLICABLE

Paired deltas recomputed from stored arm raw metrics (`assert_deltas_match_stored`).

`local_contribution_observed` requires full Local→forward→Online receive→Online deliver chain.

## Five-Task Paired Pilot (P1-A)

| Mode | Status |
|---|---|
| Offline injected pipeline | 5 pairs complete (`HARNESS_READY_NOT_LIVE_MEASURED`) |
| Live same-provider Online arms | blocked by Online auth (same blocker as vertical) |

Evidence: `paired_results.jsonl`, `paired_summary.json`

## Tests

Focused Gate1+2 + smoke + provenance regressions (see `focused_tests.json` after suite run).

## Claim Boundary

| Flag | Value |
|---|---|
| real_local_only_advisor_proven | true |
| real_local_online_vertical_proven | false |
| five_task_live_paired_pipeline_complete | false |
| measurement_provenance_complete | true |
| proven_*_savings | false |
| production_ready / public_claim_allowed | false |

## Terminal States

```text
LOCAL_ONLY_LIVE_STATUS = PROVEN
LOCAL_ONLINE_LIVE_STATUS = IMPLEMENTED_NOT_LIVE_PROVEN_ONLINE_AUTH_BLOCKED
PAIRED_PILOT_STATUS = HARNESS_READY_NOT_LIVE_MEASURED
VALUE_CLAIM_STATUS = NOT_CLAIMED
NEXUS_REAL_HYBRID_PAIRED_PILOT_COMPLETE = false
  # false until live Local+Online vertical and live five-task paired criteria are met
```

## Next Benchmark

1. Restore eligible Online provider auth (Gemini Antigravity migration or alternate approved CLI).
2. Re-run vertical via UR with Online deliver true.
3. Run five-task live paired arms A/B with same Online provider/model/revision.
4. Only then evaluate proven_*_savings from live rows.
