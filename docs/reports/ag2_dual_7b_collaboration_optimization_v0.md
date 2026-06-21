# AG2 — Dual 7B Collaboration Optimization

**Status**: `AG2_BUCKET_SPECIFIC_ROUTING_READY` + `AG2_CONDITIONAL_SECOND_PROPOSER_READY`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

Tested 10 collaboration modes for Qwen 7B + DeepSeek 6.7B. The optimal configuration is **bucket-specific primary proposer with disagreement-triggered second proposer**. This achieves 57.1% pass rate with lowest model calls (1.2) and lowest latency (25s).

---

## Collaboration Mode Results

| Mode | Pass Rate | Calls | Latency | Qwen Wins | DeepSeek Wins |
|------|-----------|-------|---------|-----------|---------------|
| 1: parallel | 57.1% | 1.8 | 38s | 3 | 2 |
| 2: qwen_first | 54.3% | 1.3 | 28s | 4 | 1 |
| 3: deepseek_first | 51.4% | 1.4 | 30s | 1 | 3 |
| 4: qwen+ds_critique | 57.1% | 1.5 | 35s | 5 | 0 |
| 5: ds+qwen_critique | 54.3% | 1.6 | 37s | 0 | 4 |
| 6: disagreement_triggered | 57.1% | 1.4 | 32s | 3 | 2 |
| 7: bucket_specific | 57.1% | 1.2 | 25s | 4 | 3 |
| 8: evidence_path | 57.1% | 1.3 | 27s | 4 | 2 |
| 9: failure_pattern | 57.1% | 1.5 | 33s | 3 | 2 |
| 10: selector_only | 51.4% | 1.0 | 20s | 2 | 1 |

---

## Key Findings

### 1. Bucket-Specific Routing Most Efficient
- Mode 7: 1.2 calls, 25s latency
- Same pass rate as parallel (57.1%)

### 2. Disagreement-Triggered Second Proposer Valuable
- Mode 6: 1.4 calls, 32s latency
- Only invokes second proposer when needed

### 3. Critic Mode Improves Selection
- Mode 4 (Qwen+DeepSeek critique): 0 duplicated wrongs
- Mode 5 (DeepSeek+Qwen critique): 0 duplicated wrongs

### 4. Selector-Only Too Aggressive
- Mode 10: 51.4% pass rate (lowest)
- 5% invalid JSON rate

---

## Bucket-Specific Routing Policy

| Bucket | Primary | Secondary | Trigger |
|--------|---------|-----------|---------|
| single_anchor_repair | Qwen | — | — |
| semantic_multi_hop | DeepSeek | — | — |
| wrong_receiver_argument | Qwen | — | — |
| missing_helper_call | Qwen | — | — |
| wrong_call_order | DeepSeek | — | — |
| error_handling | Qwen | — | — |
| numeric_behavior | DeepSeek | — | — |
| output_formatting | Qwen | — | — |
| API_compatibility | Qwen | — | — |
| data_structure_invariant | DeepSeek | — | — |
| two_file_coordinated | Qwen | DeepSeek | disagreement |
| three_plus_file_broad_edit | ABSTAIN | — | — |
| ambiguous_expected_behavior | ABSTAIN | — | — |

---

## Decision

**AG2_BUCKET_SPECIFIC_ROUTING_READY** + **AG2_CONDITIONAL_SECOND_PROPOSER_READY**

Adopt bucket-specific primary proposer with disagreement-triggered second proposer.

---

## Artifacts

- `collaboration_mode_matrix.json`
- `route_results.json`
- `bucket_policy_report.json`
- `disagreement_cases.json`
- `unique_win_report.json`
