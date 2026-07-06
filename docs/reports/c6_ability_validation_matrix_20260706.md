# C6 Ability Validation Matrix Report

**status**: C6_ABILITY_VALIDATION_MATRIX_PASS
**date**: 2026-07-06

## 10-Combination Result Table

### Current-Proof (6 combinations)

| Combination | Models | Duration | Winner Selected | Apply Status | Verifier | Solved | Failure Class |
|---|---|---|---|---|---|---|---|
| A2 | qwen+ornith | 94s | ✅ | applied | fail | ❌ | no_blocks_found |
| A3 | qwen+qwythos | 250s | ✅ | applied | fail | ❌ | verification_failed |
| A4 | deepseek+ornith | 266s | ✅ | applied | fail | ❌ | verification_failed |
| A5 | deepseek+qwythos | 134s | ✅ | applied | fail | ❌ | verification_failed |
| B2 | qwen+deepseek+qwythos | 312s | ✅ | applied | fail | ❌ | verification_failed |
| B3 | qwen+ornith+qwythos | 343s | ✅ | applied | fail | ❌ | verification_failed |

### Historical Reference (4 combinations)

| Combination | Models | Duration | Winner Selected | Apply Status | Verifier | Solved | Failure Class |
|---|---|---|---|---|---|---|---|
| A1 | qwen+deepseek | — | ✅ | applied | fail | ❌ | verification_failed |
| A6 | ornith+qwythos | — | ✅ | applied | fail | ❌ | verification_failed |
| B1 | qwen+deepseek+ornith | — | ✅ | applied | fail | ❌ | verification_failed |
| B4 | deepseek+ornith+qwythos | — | ✅ | applied | fail | ❌ | verification_failed |

## Grouped Failure Taxonomy

### Current-Proof Only

| Failure Class | Count | Combinations |
|---|---|---|
| `verification_failed` | 5 | A3, A4, A5, B2, B3 |
| `no_blocks_found` | 1 | A2 |
| **Total** | **6** | |

### Historical Reference

| Failure Class | Count | Combinations |
|---|---|---|
| `verification_failed` | 4 | A1, A6, B1, B4 |
| **Total** | **4** | |

### Combined

| Failure Class | Current | Historical | Total |
|---|---|---|---|
| `verification_failed` | 5 | 4 | 9 |
| `no_blocks_found` | 1 | 0 | 1 |
| **Total** | **6** | **4** | **10** |

## Evidence Layers

| Layer | Current | Historical | Total |
|---|---|---|---|
| **Wiring proof** | ✅ 6/6 | ✅ 4/4 | ✅ 10/10 |
| **Telemetry proof** | ✅ 6/6 | ✅ 4/4 | ✅ 10/10 |
| **Solve proof** | ❌ 0/6 | ❌ 0/4 | ❌ 0/10 |

## Solve-Lane Outcome Summary (Current-Proof)

- **Solved**: 0/6 combinations
- **Winner selected**: 6/6 combinations (committee always picks a winner)
- **Apply succeeded**: 6/6 combinations
- **Verifier failed**: 6/6 combinations (all patches failed verification)

## Failure Classification

| Category | Definition | Count | Example |
|---|---|---|---|
| **Unsolved semantic failure** | apply success + verifier fail | 9 | A1, A3-A6, B1-B4 |
| **Format failure** | no valid SEARCH/REPLACE blocks | 1 | A2 |
| **Wiring failure** | route/pipeline not connected | 0 | — |

**Key distinction**: `apply_success + verifier_fail` is an **unsolved semantic failure** (model capability issue), NOT a wiring failure. The pipeline works correctly — the model's patch doesn't fix the bug.

## Statements

- **Ability comparison justified**: All 10 combinations have comparable telemetry and can be compared.
- **Solve parity claim NOT allowed**: 0/10 solve rate demonstrates no combination has solve capability on this task.
- **Wiring complete**: All combinations run through the full Nexus pipeline.
- **No production claim**: Only wiring and telemetry truth established.
- **No route change**: Only analysis of existing results.
