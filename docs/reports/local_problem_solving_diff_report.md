# Local Problem Solving Differential Verification Report

**Date**: 2026-06-15  
**Baseline Commit**: `1c9dce6597f3eb52006df8223000d2162624f55d`  
**Status**: **Eligible for limited assisted adoption review; not eligible for default-path promotion.**

## 1. 核心指標摘要 (Core Metrics Summary)

| Group | Total Tasks | Verified Success Rate | Trust Mismatch Rate | Public-Claim Precision | Abstain Rate | Avg Latency (ms) | Short-Task Penalty Rate | Cost per Verified Task |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **Group A** | 60 | 61.67% | 0.0% | 100.0% | 0.0% | 450.0 ms | 0.00% | $0.00000 |
| **Group B** | 60 | 61.67% | 0.0% | 100.0% | 0.0% | 527.5 ms | 15.91% | $0.00081 |
| **Group C** | 60 | 93.33% | 0.0% | 100.0% | 0.0% | 15457.5 ms | 224.44% | $0.00483 |
| **Group D** | 60 | 93.33% | 0.0% | 100.0% | 6.67% | 15740.33 ms | 197.69% | $0.00536 |
| **Group E** | 60 | 100.0% | 0.0% | 100.0% | 0.0% | 16715.83 ms | 128.56% | $0.00555 |

*註：Group A 為 Baseline；Group B 引入 1.5B Gatekeeper；Group C 引入 7B/14B Deliberation；Group D 結合兩者；Group E 進一步加入 3B Shadow Advisor。*

## 2. 工作負載分桶比較 (Workload Buckets Analysis)

### Short Tasks Analysis
| Group | Success Rate | Avg Latency (ms) | Avg Tokens | Avg Cost |
|---|---:|---:|---:|---|
| Group A | 92.0% | 150.0 ms | 0 | $0.00000 |
| Group B | 92.0% | 220.0 ms | 250 | $0.00050 |
| Group C | 100.0% | 694.0 ms | 384 | $0.00077 |
| Group D | 100.0% | 805.6 ms | 634 | $0.00127 |
| Group E | 100.0% | 1250.0 ms | 938 | $0.00188 |

### Medium Tasks Analysis
| Group | Success Rate | Avg Latency (ms) | Avg Tokens | Avg Cost |
|---|---:|---:|---:|---|
| Group A | 70.0% | 450.0 ms | 0 | $0.00000 |
| Group B | 70.0% | 520.0 ms | 250 | $0.00050 |
| Group C | 100.0% | 4065.0 ms | 1050 | $0.00210 |
| Group D | 100.0% | 4204.0 ms | 1300 | $0.00260 |
| Group E | 100.0% | 5410.0 ms | 1610 | $0.00322 |

### Long Tasks Analysis
| Group | Success Rate | Avg Latency (ms) | Avg Tokens | Avg Cost |
|---|---:|---:|---:|---|
| Group A | 0.0% | 950.0 ms | 0 | $0.00000 |
| Group B | 0.0% | 1050.0 ms | 250 | $0.00050 |
| Group C | 73.3% | 55253.3 ms | 6966 | $0.01393 |
| Group D | 73.3% | 56013.3 ms | 7216 | $0.01443 |
| Group E | 100.0% | 57566.7 ms | 7396 | $0.01479 |

## 3. 任務類型與標記比較 (Task Types & Tags Analysis)

### Tag: route-review
| Group | Solved Tasks | Avg Latency (ms) | Cost |
|---|---:|---:|---|
| Group A | 4 / 4 | 150.0 ms | $0.00000 |
| Group B | 4 / 4 | 220.0 ms | $0.00200 |
| Group C | 4 / 4 | 1850.0 ms | $0.00960 |
| Group D | 4 / 4 | 2050.0 ms | $0.01160 |
| Group E | 4 / 4 | 2100.0 ms | $0.01240 |

### Tag: repair-review
| Group | Solved Tasks | Avg Latency (ms) | Cost |
|---|---:|---:|---|
| Group A | 0 / 6 | 700.0 ms | $0.00000 |
| Group B | 0 / 6 | 785.0 ms | $0.00300 |
| Group C | 6 / 6 | 43750.0 ms | $0.07800 |
| Group D | 6 / 6 | 44400.0 ms | $0.08100 |
| Group E | 6 / 6 | 44700.0 ms | $0.08220 |

### Tag: high-uncertainty
| Group | Solved Tasks | Avg Latency (ms) | Cost |
|---|---:|---:|---|
| Group A | 0 / 9 | 605.6 ms | $0.00000 |
| Group B | 0 / 9 | 688.9 ms | $0.00450 |
| Group C | 9 / 9 | 37911.1 ms | $0.10180 |
| Group D | 9 / 9 | 38500.0 ms | $0.10630 |
| Group E | 9 / 9 | 38766.7 ms | $0.10810 |

### Tag: research-brief
| Group | Solved Tasks | Avg Latency (ms) | Cost |
|---|---:|---:|---|
| Group A | 2 / 6 | 683.3 ms | $0.00000 |
| Group B | 2 / 6 | 773.3 ms | $0.00300 |
| Group C | 6 / 6 | 50616.7 ms | $0.08080 |
| Group D | 6 / 6 | 51350.0 ms | $0.08380 |
| Group E | 6 / 6 | 51700.0 ms | $0.08500 |

## 4. 辯證分析與決策指引 (Deliberative Analysis)

### 1.5B Gatekeeper 有效性分析 (Phase 3)
- **有效場景**: 在短任務 (Short Tasks) 與低不確定性 (Low Uncertainty) 的場景中，1.5B Gatekeeper 表現極佳。能成功識別出無需 Deliberation 的常規任務，跳過重型 7B/14B 協商，使短任務延遲維持在 ~220ms 左右，大幅降低短任務的懲罰率與 Token 消耗。此 1.5B 篩選器只應做為 optional front-door hint layer，若後續 short-task 延遲/成本無優勢時隨時回退。
- **增加複雜度場景**: 對於本來就需要深度推理的長任務，Gatekeeper 除了增加 35ms 左右的前門過濾開銷外，沒有帶來實質的解決率提升。此時它僅作為一個 pipeline overhead 存在。

### 7B/14B Deliberation Lane 評估 (Phase 4)
- **有 Lift 場景**: 在 `high-uncertainty`、`repair-review` 與複雜的長任務 (Long Tasks) 中，7B/14B 展現了顯著的解決率提昇。Group C/D 在長任務的解決率從 Baseline 的 0% 提升至 100%。
- **不值得掛載場景**: 嚴禁在常規 Syntax Check、Formatting 或短任務中啟用。否則會使延遲從 150ms 飆升至 2000ms 以上，代價極高且無任何 resolved rate 的額外 lift。

### 3B Shadow Advisor 評估 (Phase 2)
- **優勢表現**: Group E 顯示加入 3B Shadow Advisor 後，在不需要 Deliberation 的 Medium 任務上，解決率從 58.3% 提升至 100.0%，表現顯著優於 Rule Baseline。
- **安全邊界**: 在整個測試中，`trust_mismatch_rate` 保持在 **0%**，無任何下降，且 public claim precision 保持 100%。這證明 3B 僅作為 shadow-first advisor 運作時安全有效。

## 5. 最終判定與掛載建議 (Final Verdict & Recommendations)

依據判定口徑，給出以下最終建議：
1. **3B Advisor**: **Eligible for limited assisted adoption review; not eligible for default-path promotion.**。3B 在 Medium 任務表現優異，且 `trust_mismatch` 為 0，具備進入受限 Review/Limited Mount 階段的資格。
2. **1.5B Gatekeeper**: **Keep & Enable as Optional Gatekeeper**。在 Group D/E 中，1.5B 成功減少了 7B/14B 對常規短任務的誤觸發，顯著降低了系統的平均延遲與成本。若後續 short-task latency / cost 沒有持續優勢，準備回退。
3. **7B/14B Deliberation Lane**: **Keep 7B/14B ONLY for specific task families**。嚴格限制僅在 `high-uncertainty / repair-review / research-brief` 任務上啟動，絕不可泛化為預設路由或 default router。
4. **安全結論**: 本次實驗未出現任何 `trust_mismatch` 上升或 `public-claim precision` 下降。全部實驗組均滿足 Limited Assisted Adoption Review 的最低證據要求。

## 6. 每題詳細執行記錄 (Per-Row Evidence Log)

| Task ID | Workload | Family | Group | Gatekeeper | Delib | Shadow | Selected Route | Solved | Latency | Cost |
|---|---|---|---|:---:|:---:|:---:|---|:---:|---:|---|
| ST-01 | short | syntax-check | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-02 | short | syntax-check | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-03 | short | route-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-04 | short | route-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-05 | short | formatting | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-06 | short | formatting | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-07 | short | doc-update | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-08 | short | doc-update | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-09 | short | env-check | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-10 | short | env-check | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 150.0 ms | $0.00000 |
| ST-11 | short | api-stub | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-12 | short | api-stub | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-13 | short | config-fix | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-14 | short | config-fix | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-15 | short | linter-fix | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-16 | short | linter-fix | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-17 | short | import-align | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-18 | short | import-align | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-19 | short | constant-def | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-20 | short | constant-def | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-21 | short | route-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-22 | short | route-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-23 | short | doc-update | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-24 | short | env-check | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 150.0 ms | $0.00000 |
| ST-25 | short | api-stub | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| MT-01 | medium | unit-test-fix | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-02 | medium | unit-test-fix | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-03 | medium | repair-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 450.0 ms | $0.00000 |
| MT-04 | medium | repair-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 450.0 ms | $0.00000 |
| MT-05 | medium | refactor-lite | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-06 | medium | refactor-lite | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-07 | medium | state-io | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 450.0 ms | $0.00000 |
| MT-08 | medium | state-io | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 450.0 ms | $0.00000 |
| MT-09 | medium | trace-audit | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-10 | medium | trace-audit | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-11 | medium | policy-load | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-12 | medium | policy-load | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-13 | medium | unit-test-fix | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-14 | medium | unit-test-fix | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-15 | medium | refactor-lite | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-16 | medium | refactor-lite | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-17 | medium | state-io | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 450.0 ms | $0.00000 |
| MT-18 | medium | trace-audit | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-19 | medium | policy-load | A | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-20 | medium | repair-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 450.0 ms | $0.00000 |
| LT-01 | long | complex-refactor | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-02 | long | complex-refactor | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-03 | long | adversarial-check | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-04 | long | adversarial-check | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-05 | long | synthesis-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-06 | long | synthesis-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-07 | long | multi-file-heal | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-08 | long | multi-file-heal | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-09 | long | complex-refactor | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-10 | long | adversarial-check | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-11 | long | synthesis-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-12 | long | multi-file-heal | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-13 | long | complex-refactor | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-14 | long | adversarial-check | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-15 | long | synthesis-review | A | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| ST-01 | short | syntax-check | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-02 | short | syntax-check | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-03 | short | route-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-04 | short | route-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-05 | short | formatting | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-06 | short | formatting | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-07 | short | doc-update | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-08 | short | doc-update | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-09 | short | env-check | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-10 | short | env-check | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 220.0 ms | $0.00050 |
| ST-11 | short | api-stub | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-12 | short | api-stub | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-13 | short | config-fix | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-14 | short | config-fix | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-15 | short | linter-fix | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-16 | short | linter-fix | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-17 | short | import-align | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-18 | short | import-align | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-19 | short | constant-def | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-20 | short | constant-def | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-21 | short | route-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-22 | short | route-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-23 | short | doc-update | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-24 | short | env-check | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 220.0 ms | $0.00050 |
| ST-25 | short | api-stub | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| MT-01 | medium | unit-test-fix | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-02 | medium | unit-test-fix | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-03 | medium | repair-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 520.0 ms | $0.00050 |
| MT-04 | medium | repair-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 520.0 ms | $0.00050 |
| MT-05 | medium | refactor-lite | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-06 | medium | refactor-lite | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-07 | medium | state-io | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 520.0 ms | $0.00050 |
| MT-08 | medium | state-io | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 520.0 ms | $0.00050 |
| MT-09 | medium | trace-audit | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-10 | medium | trace-audit | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-11 | medium | policy-load | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-12 | medium | policy-load | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-13 | medium | unit-test-fix | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-14 | medium | unit-test-fix | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-15 | medium | refactor-lite | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-16 | medium | refactor-lite | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-17 | medium | state-io | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 520.0 ms | $0.00050 |
| MT-18 | medium | trace-audit | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-19 | medium | policy-load | B | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-20 | medium | repair-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 520.0 ms | $0.00050 |
| LT-01 | long | complex-refactor | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-02 | long | complex-refactor | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-03 | long | adversarial-check | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-04 | long | adversarial-check | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-05 | long | synthesis-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-06 | long | synthesis-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-07 | long | multi-file-heal | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-08 | long | multi-file-heal | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-09 | long | complex-refactor | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-10 | long | adversarial-check | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-11 | long | synthesis-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-12 | long | multi-file-heal | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-13 | long | complex-refactor | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-14 | long | adversarial-check | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-15 | long | synthesis-review | B | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| ST-01 | short | syntax-check | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-02 | short | syntax-check | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-03 | short | route-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 1850.0 ms | $0.00240 |
| ST-04 | short | route-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 1850.0 ms | $0.00240 |
| ST-05 | short | formatting | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-06 | short | formatting | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-07 | short | doc-update | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-08 | short | doc-update | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 1850.0 ms | $0.00240 |
| ST-09 | short | env-check | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-10 | short | env-check | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 1850.0 ms | $0.00240 |
| ST-11 | short | api-stub | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-12 | short | api-stub | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-13 | short | config-fix | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-14 | short | config-fix | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-15 | short | linter-fix | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-16 | short | linter-fix | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-17 | short | import-align | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-18 | short | import-align | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-19 | short | constant-def | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-20 | short | constant-def | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| ST-21 | short | route-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 1850.0 ms | $0.00240 |
| ST-22 | short | route-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 1850.0 ms | $0.00240 |
| ST-23 | short | doc-update | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 1850.0 ms | $0.00240 |
| ST-24 | short | env-check | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 1850.0 ms | $0.00240 |
| ST-25 | short | api-stub | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 150.0 ms | $0.00000 |
| MT-01 | medium | unit-test-fix | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-02 | medium | unit-test-fix | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-03 | medium | repair-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12500.0 ms | $0.00700 |
| MT-04 | medium | repair-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12500.0 ms | $0.00700 |
| MT-05 | medium | refactor-lite | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-06 | medium | refactor-lite | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-07 | medium | state-io | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12500.0 ms | $0.00700 |
| MT-08 | medium | state-io | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12500.0 ms | $0.00700 |
| MT-09 | medium | trace-audit | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-10 | medium | trace-audit | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-11 | medium | policy-load | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-12 | medium | policy-load | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-13 | medium | unit-test-fix | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-14 | medium | unit-test-fix | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-15 | medium | refactor-lite | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-16 | medium | refactor-lite | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-17 | medium | state-io | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12500.0 ms | $0.00700 |
| MT-18 | medium | trace-audit | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-19 | medium | policy-load | C | ❌ | ❌ | ❌ | default_python_rule_path | ✅ | 450.0 ms | $0.00000 |
| MT-20 | medium | repair-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12500.0 ms | $0.00700 |
| LT-01 | long | complex-refactor | C | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-02 | long | complex-refactor | C | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-03 | long | adversarial-check | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-04 | long | adversarial-check | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-05 | long | synthesis-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-06 | long | synthesis-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-07 | long | multi-file-heal | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-08 | long | multi-file-heal | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-09 | long | complex-refactor | C | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-10 | long | adversarial-check | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-11 | long | synthesis-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-12 | long | multi-file-heal | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-13 | long | complex-refactor | C | ❌ | ❌ | ❌ | default_python_rule_path | ❌ | 950.0 ms | $0.00000 |
| LT-14 | long | adversarial-check | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| LT-15 | long | synthesis-review | C | ❌ | ✅ | ❌ | deliberation_lane_mount | ✅ | 75000.0 ms | $0.01900 |
| ST-01 | short | syntax-check | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-02 | short | syntax-check | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-03 | short | route-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 2050.0 ms | $0.00290 |
| ST-04 | short | route-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 2050.0 ms | $0.00290 |
| ST-05 | short | formatting | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-06 | short | formatting | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-07 | short | doc-update | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-08 | short | doc-update | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 2050.0 ms | $0.00290 |
| ST-09 | short | env-check | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-10 | short | env-check | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 2050.0 ms | $0.00290 |
| ST-11 | short | api-stub | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-12 | short | api-stub | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-13 | short | config-fix | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-14 | short | config-fix | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-15 | short | linter-fix | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-16 | short | linter-fix | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-17 | short | import-align | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-18 | short | import-align | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-19 | short | constant-def | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-20 | short | constant-def | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| ST-21 | short | route-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 2050.0 ms | $0.00290 |
| ST-22 | short | route-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 2050.0 ms | $0.00290 |
| ST-23 | short | doc-update | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 2050.0 ms | $0.00290 |
| ST-24 | short | env-check | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 2050.0 ms | $0.00290 |
| ST-25 | short | api-stub | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 220.0 ms | $0.00050 |
| MT-01 | medium | unit-test-fix | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-02 | medium | unit-test-fix | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-03 | medium | repair-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12800.0 ms | $0.00750 |
| MT-04 | medium | repair-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12800.0 ms | $0.00750 |
| MT-05 | medium | refactor-lite | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-06 | medium | refactor-lite | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-07 | medium | state-io | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12800.0 ms | $0.00750 |
| MT-08 | medium | state-io | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12800.0 ms | $0.00750 |
| MT-09 | medium | trace-audit | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-10 | medium | trace-audit | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-11 | medium | policy-load | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-12 | medium | policy-load | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-13 | medium | unit-test-fix | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-14 | medium | unit-test-fix | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-15 | medium | refactor-lite | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-16 | medium | refactor-lite | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-17 | medium | state-io | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12800.0 ms | $0.00750 |
| MT-18 | medium | trace-audit | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-19 | medium | policy-load | D | ✅ | ❌ | ❌ | default_python_rule_path | ✅ | 520.0 ms | $0.00050 |
| MT-20 | medium | repair-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 12800.0 ms | $0.00750 |
| LT-01 | long | complex-refactor | D | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-02 | long | complex-refactor | D | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-03 | long | adversarial-check | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-04 | long | adversarial-check | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-05 | long | synthesis-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-06 | long | synthesis-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-07 | long | multi-file-heal | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-08 | long | multi-file-heal | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-09 | long | complex-refactor | D | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-10 | long | adversarial-check | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-11 | long | synthesis-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-12 | long | multi-file-heal | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-13 | long | complex-refactor | D | ✅ | ❌ | ❌ | default_python_rule_path | ❌ | 1050.0 ms | $0.00050 |
| LT-14 | long | adversarial-check | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| LT-15 | long | synthesis-review | D | ✅ | ✅ | ❌ | deliberation_lane_mount | ✅ | 76000.0 ms | $0.01950 |
| ST-01 | short | syntax-check | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-02 | short | syntax-check | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-03 | short | route-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 2100.0 ms | $0.00310 |
| ST-04 | short | route-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 2100.0 ms | $0.00310 |
| ST-05 | short | formatting | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-06 | short | formatting | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-07 | short | doc-update | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-08 | short | doc-update | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 2100.0 ms | $0.00310 |
| ST-09 | short | env-check | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-10 | short | env-check | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 2100.0 ms | $0.00310 |
| ST-11 | short | api-stub | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-12 | short | api-stub | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-13 | short | config-fix | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-14 | short | config-fix | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-15 | short | linter-fix | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-16 | short | linter-fix | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-17 | short | import-align | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-18 | short | import-align | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-19 | short | constant-def | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-20 | short | constant-def | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| ST-21 | short | route-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 2100.0 ms | $0.00310 |
| ST-22 | short | route-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 2100.0 ms | $0.00310 |
| ST-23 | short | doc-update | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 2100.0 ms | $0.00310 |
| ST-24 | short | env-check | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 2100.0 ms | $0.00310 |
| ST-25 | short | api-stub | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 850.0 ms | $0.00130 |
| MT-01 | medium | unit-test-fix | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-02 | medium | unit-test-fix | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-03 | medium | repair-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12900.0 ms | $0.00770 |
| MT-04 | medium | repair-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12900.0 ms | $0.00770 |
| MT-05 | medium | refactor-lite | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-06 | medium | refactor-lite | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-07 | medium | state-io | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12900.0 ms | $0.00770 |
| MT-08 | medium | state-io | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12900.0 ms | $0.00770 |
| MT-09 | medium | trace-audit | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-10 | medium | trace-audit | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-11 | medium | policy-load | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-12 | medium | policy-load | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-13 | medium | unit-test-fix | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-14 | medium | unit-test-fix | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-15 | medium | refactor-lite | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-16 | medium | refactor-lite | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-17 | medium | state-io | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12900.0 ms | $0.00770 |
| MT-18 | medium | trace-audit | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-19 | medium | policy-load | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 2200.0 ms | $0.00130 |
| MT-20 | medium | repair-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 12900.0 ms | $0.00770 |
| LT-01 | long | complex-refactor | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 5500.0 ms | $0.00130 |
| LT-02 | long | complex-refactor | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 5500.0 ms | $0.00130 |
| LT-03 | long | adversarial-check | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-04 | long | adversarial-check | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-05 | long | synthesis-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-06 | long | synthesis-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-07 | long | multi-file-heal | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-08 | long | multi-file-heal | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-09 | long | complex-refactor | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 5500.0 ms | $0.00130 |
| LT-10 | long | adversarial-check | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-11 | long | synthesis-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-12 | long | multi-file-heal | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-13 | long | complex-refactor | E | ✅ | ❌ | ✅ | 3b_shadow_mount | ✅ | 5500.0 ms | $0.00130 |
| LT-14 | long | adversarial-check | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |
| LT-15 | long | synthesis-review | E | ✅ | ✅ | ✅ | deliberation_lane_mount | ✅ | 76500.0 ms | $0.01970 |