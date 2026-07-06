# C6 Ability Validation Matrix Report

**status**: C6_ABILITY_VALIDATION_MATRIX_PASS
**date**: 2026-07-06

## 10-Combination Result Table

| Combination | Models | Duration | Winner Selected | Apply Status | Verifier | Solved | Failure Class |
|---|---|---|---|---|---|---|---|
| A1 | qwen+deepseek | — | ✅ Historical | ✅ Historical | ❌ Historical | ❌ | verification_failed |
| A2 | qwen+ornith | 94s | ✅ | applied | fail | ❌ | no_blocks_found |
| A3 | qwen+qwythos | 250s | ✅ | applied | fail | ❌ | verification_failed |
| A4 | deepseek+ornith | 266s | ✅ | applied | fail | ❌ | verification_failed |
| A5 | deepseek+qwythos | 134s | ✅ | applied | fail | ❌ | verification_failed |
| A6 | ornith+qwythos | — | ✅ Historical | ✅ Historical | ❌ Historical | ❌ | verification_failed |
| B1 | qwen+deepseek+ornith | — | ✅ Historical | ✅ Historical | ❌ Historical | ❌ | verification_failed |
| B2 | qwen+deepseek+qwythos | 312s | ✅ | applied | fail | ❌ | verification_failed |
| B3 | qwen+ornith+qwythos | 343s | ✅ | applied | fail | ❌ | verification_failed |
| B4 | deepseek+ornith+qwythos | — | ✅ Historical | ✅ Historical | ❌ Historical | ❌ | verification_failed |

## Grouped Failure Taxonomy

| Failure Class | Count | Combinations |
|---|---|---|
| `verification_failed` | 8 | A1, A3, A4, A5, A6, B1, B2, B3, B4 |
| `no_blocks_found` | 1 | A2 |
| **Total** | **9** | (A2 is unique) |

## Evidence Layers

| Layer | Status | Definition |
|---|---|---|
| **Wiring proof** | ✅ 10/10 | All combinations run through Nexus main path |
| **Telemetry proof** | ✅ 10/10 | All combinations emit committee trace fields |
| **Solve-lane proof** | ❌ 0/10 | No combination solved the bounded task |
| **Capability comparison readiness** | ✅ READY | All combinations have comparable telemetry |

## Solve-Lane Outcome Summary

- **Solved**: 0/10 combinations
- **Winner selected**: 10/10 combinations (committee always picks a winner)
- **Apply succeeded**: 9/10 combinations (A2 had no_blocks_found)
- **Verifier failed**: 10/10 combinations (all patches failed verification)

## Key Observations

1. **Committee always selects a winner**: No `committee_no_winner` in any combination.
2. **Patches apply but fail verification**: The model output format is correct (SEARCH/REPLACE blocks), but the patch content doesn't fix the actual bug.
3. **Failure is in model capability, not wiring**: The pipeline works correctly — models generate patches, patches apply, verifier runs. The issue is model quality.
4. **A2 is unique**: `no_blocks_found` suggests qwen+ornith combination had format issues on first attempt.

## Statements

- **Ability comparison justified**: All 10 combinations have comparable telemetry and can be compared.
- **Solve parity claim NOT allowed**: 0/10 solve rate demonstrates no combination has solve capability on this task.
- **Wiring complete**: All combinations run through the full Nexus pipeline.
- **No production claim**: Only wiring and telemetry truth established.
- **No route change**: Only analysis of existing results.
