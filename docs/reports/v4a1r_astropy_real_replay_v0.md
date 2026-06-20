# V4-A.1R Astropy Real Replay — Final Report

## Status: V4A1R_REAL_REPLAY_PASS_INTERNAL_ONLY

## Summary

One real execution-backed replay completed for MC001 astropy-13236 using:
- Ollama qwen2.5-coder:7b (local, no cloud API)
- astropy v5.2.1 source checkout (SHA: 95df21d)
- Hardened Roadmap v3 pipeline

## Results

| Field | Value |
|-------|-------|
| task_id | MC001 |
| execution_mode | real |
| model_used | qwen2.5-coder:7b |
| model_calls | 1 |
| cloud_api_used | false |
| match_authority | verbatim |
| success_attribution | model_patch_success |
| task_scoped | true |
| structured_packet_used | true |
| export_classification | model_patch_success_candidate |
| public_claim_allowed | false |
| training_eligible | false |

## Roadmap v3 Invariants Verified

| Invariant | Status |
|-----------|--------|
| match_authority non-null on success | ✅ verbatim |
| FUZZY_CANDIDATE_ONLY fail-closed | ✅ AssertionError raised |
| MicroVerifier task-scoped | ✅ via env_taxonomy |
| StructuredPacket wired | ✅ created |
| Export classification | ✅ model_patch_success_candidate |
| public_claim_allowed=false | ✅ |
| training_eligible=false | ✅ |

## Files Modified

- `nexus/services/local_heal/patch_applier.py` — FUZZY_CANDIDATE_ONLY precedence fix

## Test Results

- `test_patch_applier.py`: 17/17 pass (including FUZZY invariant)
- Real replay: V4A1R_REAL_REPLAY_PASS_INTERNAL_ONLY
