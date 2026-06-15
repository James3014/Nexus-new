# Limited Mount Observation Cycle 02 Report

**Date**: 2026-06-15  
**Evaluation Commit**: `65bedd4b531327c1cfb0d196d6d0b6a4eb1584bd`  
**Status**: **Eligible for limited assisted adoption review; not eligible for default-path promotion.**

## 1. 總體指標摘要 (Overall Telemetry Metrics)

- **總觀測題數 (Total Tasks)**: 30
- **限額掛載解決率 (Verified Success Rate)**: 100.00% (基準線 Baseline: 53.33%)
- **信任不匹配率 (Trust Mismatch Rate)**: 0.00%
- **公開主張精準度 (Public-Claim Precision)**: 100.00%
- **棄權率 (Abstain Rate)**: 0.00%
- **延遲增量 (E2E Latency Delta)**: +27260.00 ms
- **短任務懲罰率 (Short-Task Penalty Rate)**: 4.17%
- **每認證任務成本 (Cost per Verified Task)**: $0.00818
- **白名單命中率 (Whitelist Hit Rate)**: 100.00%
- **退避率 (Fallback Rate)**: 0.00%
- **回滾事件數 (Rollback Incidents)**: 0
- **觀測判定結論 (Observation Verdict)**: **KEEP**

## 2. 工作負載分桶比較 (Workload Buckets Analysis)

| Workload Bucket | Tasks | Baseline Success | Limited Mount Success | Avg Latency (ms) | Total Cost |
|---|---:|---:|---:|---:|---|
| Short | 10 | 100.0% | 100.0% | 840.0 ms | $0.01280 |
| Medium | 10 | 60.0% | 100.0% | 6390.0 ms | $0.03768 |
| Long | 10 | 0.0% | 100.0% | 76100.0 ms | $0.19500 |

## 3. 標記類型細分統計 (Tag Breakdown)

| Task Tag | Tasks | Baseline Success | Limited Mount Success | Avg Latency (ms) | Cost |
|---|---:|---:|---:|---:|---|
| normal-short | 11 | 100.0% | 100.0% | 1316.4 ms | $0.01408 |
| route-review | 5 | 100.0% | 100.0% | 1364.0 ms | $0.00640 |
| repair-review | 7 | 0.0% | 100.0% | 39900.0 ms | $0.08850 |
| high-uncertainty | 4 | 0.0% | 100.0% | 76100.0 ms | $0.07800 |
| research-brief | 3 | 0.0% | 100.0% | 76100.0 ms | $0.05850 |

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
| OBS2-ST-01 | short | syntax-check | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-ST-02 | short | syntax-check | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-ST-03 | short | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-ST-04 | short | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-ST-05 | short | formatting | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-ST-06 | short | formatting | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-ST-07 | short | doc-update | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-ST-08 | short | doc-update | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-ST-09 | short | env-check | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-ST-10 | short | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 840.0 ms | $0.00128 |
| OBS2-MT-01 | medium | unit-test-fix | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2150.0 ms | $0.00128 |
| OBS2-MT-02 | medium | unit-test-fix | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2150.0 ms | $0.00128 |
| OBS2-MT-03 | medium | repair-review | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12750.0 ms | $0.00750 |
| OBS2-MT-04 | medium | repair-review | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12750.0 ms | $0.00750 |
| OBS2-MT-05 | medium | refactor-lite | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2150.0 ms | $0.00128 |
| OBS2-MT-06 | medium | refactor-lite | normal-short | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2150.0 ms | $0.00128 |
| OBS2-MT-07 | medium | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2150.0 ms | $0.00128 |
| OBS2-MT-08 | medium | route-review | route-review | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2150.0 ms | $0.00128 |
| OBS2-MT-09 | medium | repair-review | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12750.0 ms | $0.00750 |
| OBS2-MT-10 | medium | repair-review | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12750.0 ms | $0.00750 |
| OBS2-LT-01 | long | adversarial-check | high-uncertainty | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |
| OBS2-LT-02 | long | adversarial-check | high-uncertainty | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |
| OBS2-LT-03 | long | synthesis-review | research-brief | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |
| OBS2-LT-04 | long | synthesis-review | research-brief | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |
| OBS2-LT-05 | long | multi-file-heal | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |
| OBS2-LT-06 | long | multi-file-heal | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |
| OBS2-LT-07 | long | adversarial-check | high-uncertainty | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |
| OBS2-LT-08 | long | adversarial-check | high-uncertainty | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |
| OBS2-LT-09 | long | synthesis-review | research-brief | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |
| OBS2-LT-10 | long | multi-file-heal | repair-review | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76100.0 ms | $0.01950 |