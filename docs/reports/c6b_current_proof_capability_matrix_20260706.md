# C6B Current-Proof Capability Matrix Report

**status**: C6B_CURRENT_PROOF_CAPABILITY_MATRIX_PASS
**date**: 2026-07-06

## Coverage

All 11 combinations have current-proof evidence:

| Tier | Combinations | Current-Proof |
|---|---|---|
| Dual | 6 | ✅ 6/6 |
| Triple | 4 | ✅ 4/4 |
| Four-model | 1 | ✅ 1/1 |
| **Total** | **11** | **✅ 11/11** |

## Matrix

| Combo | Tier | Winner | Apply | Verifier | Solved | Primary Failure | Evidence |
|---|---|---|---|---|---|---|---|
| qwen+deepseek | dual | ✅ | ✅ | ❌ | ❌ | verification_failed | C4C-A1 |
| qwen+ornith | dual | ✅ | ✅ | ❌ | ❌ | no_blocks_found | C4C-A2-94s |
| qwen+qwythos | dual | ✅ | ✅ | ❌ | ❌ | verification_failed | C4C-A3-250s |
| deepseek+ornith | dual | ✅ | ✅ | ❌ | ❌ | verification_failed | C4C-A4-266s |
| deepseek+qwythos | dual | ✅ | ✅ | ❌ | ❌ | verification_failed | C4C-A5-134s |
| ornith+qwythos | dual | ✅ | ✅ | ❌ | ❌ | verification_failed | C4C-A6 |
| qwen+deepseek+ornith | triple | ✅ | ✅ | ❌ | ❌ | verification_failed | C4C-B1 |
| qwen+deepseek+qwythos | triple | ✅ | ✅ | ❌ | ❌ | verification_failed | C4C-B2-312s |
| qwen+ornith+qwythos | triple | ✅ | ✅ | ❌ | ❌ | verification_failed | C4C-B3-343s |
| deepseek+ornith+qwythos | triple | ✅ | ✅ | ❌ | ❌ | verification_failed | C4C-B4 |
| qwen+deepseek+ornith+qwythos | four | ✅ | ✅ | ❌ | ❌ | verification_failed | C6B-444s |

## Failure Pattern

| Bucket | Count | % | Definition |
|---|---|---|---|
| `verification_failed` | 10 | 91% | Patch applies but verifier rejects |
| `no_blocks_found` | 1 | 9% | Model didn't produce valid SEARCH/REPLACE |
| **Total** | **11** | **100%** | |

## Diagnosis

| Layer | Status | Where it stops |
|---|---|---|
| Wiring | ✅ 11/11 | All combinations reach verifier |
| Telemetry | ✅ 11/11 | All combinations emit full trace |
| Apply | ✅ 10/11 | A2 has format issue (no_blocks_found) |
| Verifier | ❌ 0/11 | All patches fail verification |
| Solve | ❌ 0/11 | No combination solves |

**The pipeline works. The models don't solve.**

## Next Target

If only one bucket to attack: **verification_failed** (91% of failures).

The model generates patches that apply correctly, but the patch content doesn't fix the actual bug. This is a model capability issue, not a wiring issue.

## Statements

- **Wiring complete**: All 11 combinations run through full Nexus pipeline.
- **Solve truth unproven**: 0/11 solve rate.
- **No production claim**: Only wiring and telemetry truth established.
- **No route change**: Only analysis of existing results.
