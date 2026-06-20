# T4.1 Model-Candidate Evidence Freeze Report

**Date**: 2026-06-18
**Verdict**: GREEN

---

## 1. T4.1 Verdict: GREEN

## 2. Frozen Model Candidate Registry
- Path: configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml
- Total candidates: 20
- Active replayable: 12
- Historical clean stale: 8

## 3. Candidate Summary

| evidence_tier | Count | replay_eligible |
|---------------|-------|-----------------|
| active_replayable | 12 | YES |
| historical_clean_source_stale | 8 | NO |

## 4. Source Revision Hygiene

| status | Count |
|--------|-------|
| source_fresh | 12 |
| source_already_patched | 8 |

## 5. Attribution Safety

| Check | Status |
|-------|--------|
| source_stale_counted_as_model_failure | NO ✓ |
| historical_clean_counted_as_current_success | NO ✓ |
| model_calls_0_counted_as_model_success | NO ✓ |
| deterministic_fallback_counted_as_model_success | NO ✓ |
| public_claim_allowed_any | NO ✓ |

## 6. T4.2 Replay Manifest
- Path: configs/model_candidates/t4_1_t4_2_clean_room_replay_manifest.yaml
- replay_eligible_count: 12
- replay_blocked_count: 8

## 7. Non-Claims
- NOT a public benchmark
- NOT Qwen solve rate
- NOT comparable to official SWE-bench
- Human review required before training/export

## 8. Recommended Next Step
T4.2 Clean-Room Replay (using replay_eligible candidates only)
