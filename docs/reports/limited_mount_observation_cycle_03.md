# Limited Mount Observation Cycle 03 Report

**Date**: 2026-06-15  
**Evaluation Commit**: `edf13b86dd39d322d77477a40afd68d47bea7cf6`  
**Status**: **Eligible for limited assisted adoption review; not eligible for default-path promotion.**

## 1. 總體指標摘要 (Overall Telemetry Metrics)

- **總觀測題數 (Total Tasks)**: 30
- **限額掛載解決率 (Verified Success Rate)**: 100.00% (基準線 Baseline: 53.33%)
- **信任不匹配率 (Trust Mismatch Rate)**: 0.00%
- **公開主張精準度 (Public-Claim Precision)**: 100.00%
- **棄權率 (Abstain Rate)**: 0.00%
- **延遲增量 (E2E Latency Delta)**: +27580.00 ms
- **短任務懲罰率 (Short-Task Penalty Rate)**: 4.07%
- **每認證任務成本 (Cost per Verified Task)**: $0.00830
- **白名單命中率 (Whitelist Hit Rate)**: 100.00%
- **退避率 (Fallback Rate)**: 0.00%
- **回滾事件數 (Rollback Incidents)**: 0
- **觀測判定結論 (Observation Verdict)**: **KEEP**

## 2. 工作負載分桶比較 (Workload Buckets Analysis)

| Workload Bucket | Tasks | Baseline Success | Limited Mount Success | Avg Latency (ms) | Total Cost |
|---|---:|---:|---:|---:|---|
| Short | 10 | 100.0% | 100.0% | 860.0 ms | $0.01320 |
| Medium | 10 | 60.0% | 100.0% | 6530.0 ms | $0.03872 |
| Long | 10 | 0.0% | 100.0% | 76900.0 ms | $0.19700 |

## 3. 標記類型細分統計 (Tag Breakdown)

| Task Tag | Tasks | Baseline Success | Limited Mount Success | Avg Latency (ms) | Cost |
|---|---:|---:|---:|---:|---|
| normal-short | 11 | 100.0% | 100.0% | 1365.5 ms | $0.01452 |
| route-review | 5 | 100.0% | 100.0% | 1416.0 ms | $0.00660 |
| repair-review | 7 | 0.0% | 100.0% | 40357.1 ms | $0.08990 |
| high-uncertainty | 4 | 0.0% | 100.0% | 76900.0 ms | $0.07880 |
| research-brief | 3 | 0.0% | 100.0% | 76900.0 ms | $0.05910 |

## 4. If / Then 治理判定核對

| If / Then 條款 | 觸發狀態 | 執行動作 / Verdict |
|---|---|---|
| **trust mismatch rate > 0** | ✅ 未觸發 | Keep |
| **public-claim precision < 100%** | ✅ 未觸發 | Keep |
| **1.5B cost advantage lost** | ✅ 未觸發 (short-task penalty 穩定) | Keep Optional 1.5B |
| **7B/14B deliberation outside whitelist** | ✅ 未觸發 (hit rate 100%) | Keep Whitelist Restriction |
| **3B维持 0 mismatch 且 verified lift** | 🎯 滿足 (Success: 100.0% vs 53.3%) | Keep Limited Assist |

## 5. 每題詳細觀測記錄 (Per-Row Evidence Log)

| Task ID | Workload | Family | Tag | Gatekeeper | Delib | Shadow | Selected Route | Solved | Latency | Cost |
|---|---|---|---|:---:|:---:|:---:|---|:---:|---:|---|
| OBS3-ST-01 | short | syntax-check | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-ST-02 | short | syntax-check | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-ST-03 | short | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-ST-04 | short | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-ST-05 | short | formatting | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-ST-06 | short | formatting | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-ST-07 | short | doc-update | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-ST-08 | short | doc-update | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-ST-09 | short | env-check | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-ST-10 | short | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 860.0 ms | $0.00132 |
| OBS3-MT-01 | medium | unit-test-fix | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2250.0 ms | $0.00132 |
| OBS3-MT-02 | medium | unit-test-fix | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2250.0 ms | $0.00132 |
| OBS3-MT-03 | medium | repair-review | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12950.0 ms | $0.00770 |
| OBS3-MT-04 | medium | repair-review | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12950.0 ms | $0.00770 |
| OBS3-MT-05 | medium | refactor-lite | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2250.0 ms | $0.00132 |
| OBS3-MT-06 | medium | refactor-lite | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2250.0 ms | $0.00132 |
| OBS3-MT-07 | medium | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2250.0 ms | $0.00132 |
| OBS3-MT-08 | medium | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2250.0 ms | $0.00132 |
| OBS3-MT-09 | medium | repair-review | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12950.0 ms | $0.00770 |
| OBS3-MT-10 | medium | repair-review | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12950.0 ms | $0.00770 |
| OBS3-LT-01 | long | adversarial-check | high-uncertainty | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |
| OBS3-LT-02 | long | adversarial-check | high-uncertainty | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |
| OBS3-LT-03 | long | synthesis-review | research-brief | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |
| OBS3-LT-04 | long | synthesis-review | research-brief | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |
| OBS3-LT-05 | long | multi-file-heal | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |
| OBS3-LT-06 | long | multi-file-heal | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |
| OBS3-LT-07 | long | adversarial-check | high-uncertainty | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |
| OBS3-LT-08 | long | adversarial-check | high-uncertainty | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |
| OBS3-LT-09 | long | synthesis-review | research-brief | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |
| OBS3-LT-10 | long | multi-file-heal | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76900.0 ms | $0.01970 |