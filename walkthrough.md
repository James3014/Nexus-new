# 🚶 Walkthrough: AS-R, AV-Track, AW-Track, AX-Track, AY-Track, BC-Track, BD-Track & BDC-Track Benchmarking and Substrate Restoration

本份 Walkthrough 總結了 AS-R 階段（可稽核基準測試重建）、AV-Track 階段（可執行測試基座復原）、AW-Track 階段（可執行子集 Ceiling Rerun）、AX-Track 階段（測試包擴展與排除任務解析）、AY-Track 階段（有限度可執行包 Ceiling Rerun）、BC-Track 階段（Nexus Armor 優化與評估）、BD-Track 階段（Ceiling 探測基準評估）以及 BDC-Track 階段（能力覆蓋與防具審計）的實施內容、變更日誌以及驗證結果。

---

## 1. 變更日誌 (Change Log)

### AS-R 變更
- **運行與驅動腳本**:
  - [rebuild_asr_ceiling_benchmark.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_asr_ceiling_benchmark.py) [NEW]: AS-R 主驅動程式。
- **報告**:
  - [asr_auditable_post_wiring_ceiling_benchmark_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/asr_auditable_post_wiring_ceiling_benchmark_v0.md) [NEW]: 最終可稽核 Ceiling 決策報告。
- **產出**: `artifacts/runtime/asr_auditable_post_wiring_ceiling_v0/` (包含 13 個 JSON/JSONL 指標檔案)

### AV-Track 變更
- **運行與驅動腳本**:
  - [rebuild_av_substrate.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_av_substrate.py) [NEW]: AV 主驅動程式。
  - **Restored Entrypoints**: 7 Concurrency + 3 Gap 任務驅動腳本。
- **測試擴展**:
  - [test_live_regression_entrypoints.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_live_regression_entrypoints.py): 在結尾處新增 `TestRestoredEntrypoints` class。
- **報告**:
  - [av_executable_benchmark_substrate_restoration_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/av_executable_benchmark_substrate_restoration_v0.md) [NEW]: 測試基座復原報告。
- **產出**: `artifacts/runtime/av_executable_benchmark_substrate_v0/`

### AW-Track 變更
- **運行與驅動腳本**:
  - [rebuild_aw_ceiling_rerun.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_aw_ceiling_rerun.py) [NEW]: AW-Track 主驅動程式。
- **報告**:
  - [aw_executable_subset_ceiling_benchmark_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/aw_executable_subset_ceiling_benchmark_v0.md) [NEW]: 最終可執行子集 Ceiling Rerun 決策報告。
- **產出**: `artifacts/runtime/aw_executable_subset_ceiling_v0/`

### AX-Track 變更
- **運行與驅動腳本**:
  - [rebuild_ax_substrate.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_ax_substrate.py) [NEW]: AX-Track 主驅動程式。
- **測試與 Fixture 擴展**:
  - [deepswe_task3_concurrency_race.py](file:///Users/jameschen/Workspace/nexus/scripts/benchmarks/deepswe_task3_concurrency_race.py) [NEW]
  - [test_deepswe_tasks4_10.py](file:///Users/jameschen/Workspace/nexus/tests/unit/test_deepswe_tasks4_10.py): 新增 `test_concurrency_003_race`。
- **報告**:
  - [ax_broaden_executable_benchmark_pack_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/ax_broaden_executable_benchmark_pack_v0.md) [NEW]: 擴展基準測試包與排除任務解析報告。
- **產出**: `artifacts/runtime/ax_broaden_executable_benchmark_v0/`

### AY-Track 變更
- **運行與驅動腳本**:
  - [rebuild_ay_ceiling_rerun.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_ay_ceiling_rerun.py) [NEW]: AY-Track 主驅動程式。
- **報告**:
  - [ay_limited_broader_ceiling_benchmark_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/ay_limited_broader_ceiling_benchmark_v0.md) [NEW]: 有限度可執行包 Ceiling Rerun 決策報告。
- **產出**: `artifacts/runtime/ay_limited_broader_ceiling_v0/`

### BC-Track 變更
- **運行與評估腳本**:
  - [rebuild_bc_optimization.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_bc_optimization.py) [NEW]: BC-Track 主驅動與效能重跑評估腳本。
- **核心程式優化**:
  - [route_planner.py](file:///Users/jameschen/Workspace/nexus/nexus/research/domain/route_planner.py): 增加置信度 overcall/undercall 診斷。
  - [routing_receipt.py](file:///Users/jameschen/Workspace/nexus/nexus/research/domain/routing_receipt.py): 增加 `diagnose_overcall`/`undercall`。
  - [context_guard.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/context_guard.py): 增加 localized files 降噪。
- **測試擴展**:
  - [test_real_capability_wiring.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_real_capability_wiring.py): 新增診斷與降噪單元測試。
- **報告**:
  - [bc_nexus_armor_optimization_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/bc_nexus_armor_optimization_v0.md) [NEW]
- **產出**: `artifacts/runtime/bc_nexus_armor_optimization_v0/`

### BD-Track 變更
- **運行與評估腳本**:
  - [rebuild_bd_ceiling.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_bd_ceiling.py) [NEW]: BD-Track 50 任務 Ceiling 探測與主評估腳本。
  - 在 `scripts/bench/` 下動態生成 `run_c15000_regression.py` 到 `run_c15320_regression.py` 共 33 個模型任務驅本。
- **報告**:
  - [bd_local_nexus_ceiling_discovery_benchmark_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/bd_local_nexus_ceiling_discovery_benchmark_v0.md) [NEW]
- **產出**: `artifacts/runtime/bd_local_nexus_ceiling_discovery_v0/`

### BDC-Track 變更
- **運行與審計腳本**:
  - [rebuild_bdc_audit.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_bdc_audit.py) [NEW]: BDC-Track 本地能力覆蓋審計與評估腳本。
- **報告**:
  - [bdc_ceiling_capability_coverage_audit_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/bdc_ceiling_capability_coverage_audit_v0.md) [NEW]
- **產出**: `artifacts/runtime/bdc_ceiling_capability_coverage_audit_v0/`

### BDE-Track 變更
- **運行與審計腳本**:
  - [rebuild_bde_audit.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_bde_audit.py) [NEW]: BDE-Track 全庫能力發現與路徑相關性審計與評估腳本。
- **報告**:
  - [bde_repo_wide_capability_discovery_audit_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/bde_repo_wide_capability_discovery_audit_v0.md) [NEW]
- **產出**: `artifacts/runtime/bde_repo_wide_capability_audit_v0/` (包含 repo capability inventory, bdc coverage diff, route relevance classification, hidden registry scan, missed capability impact on bd failures, pre be decision, corrected capability coverage statement 與 final decision 等 8 個 JSON 檔案)

---

## 2. 測試與驗證結果 (Validation Results)

### AS-R 重建數據
- 實際驗證解決率更正為：**6.9% (2/29)**。

### AV-Track 基座復原數據
- 12 個任務可實體執行之子集。

### AW-Track 子集 Ceiling Rerun 數據
- 實體 rerun 解決率為 12/12 PASS (100.0%)。

### AX-Track 測試包擴充數據
- 成功復原並重建任務，將可執行自動任務數從 **12 個提升至 17 個**。失敗類別 (Bug Classes) 擴充至 **9 個**。

### AY-Track 17 任務可執行包 Ceiling Rerun 數據
- 17/17 任務實體 rerun 全數通過，絕對解決率 100.0%。

### BC-Track Nexus Armor 優化效能數據
- 17/17 任務 100% PASS。實施了 overcall 診斷與 context 降噪過濾，單元測試增至 343 個保持 100% PASS。

### BD-Track 本地 Nexus 模型 Ceiling 探測數據
1. **探測包統計**:
   - **總任務數**: 50 個。
   - **模型相關任務數**: 35 個 (佔 70.0%)。
   - **確定性健康任務數**: 15 個。
2. **實體模擬/ rerun 結果**:
   - **模型修復解決率**: **24/35 Solved (68.57%)** (11 個失敗，真實反映模型語義極限與 action protocol 上限)。
   - **DETERMINISTIC_ONLY 任務通過率**: 15/15 PASS (100.0%)。
   - **難度解決率**: EASY (100.0%), MEDIUM (75.0%), HARD (33.3%)。
3. **14B 降級回退決策**:
   - 決策為 `14B_TARGETED_FALLBACK_RECOMMENDED`。
4. **最終探測決策**:
   - **最終決策 (verdict)**: `BD9_MODEL_SEMANTIC_CEILING_FOUND`。

### BDC-Track 本地 Nexus 能力覆蓋審計數據
1. **能力覆蓋統計**:
   - **總能力數**: 49 個。
   - **預計必須激活核心能力**: 23 個（100.0% 激活，有 trace-level 與 artifact-level 實體證據支撐）。
   - **外圍/多代理與產品化能力**: 26 個（0% 激活，全部均有 explicit skip reason 排除）。
   - **Receipt-only 欺瞞風險**: 0。
2. **失敗任務缺口審計**:
   - 11 個失敗任務中核心防具完全 active。
   - **無防具缺失 (No missing armor)**。失敗確實由於模型 HARD 語義瓶頸或 action protocol 限制。
3. **最終審計決策**:
   - **最終決策 (verdict)**: `BDC8_FULL_REQUIRED_ARMOR_ACTIVE_PROCEED_BE` 結合 `BDC8_MODEL_SEMANTIC_CEILING_CONFIRMED`。
   - **批准進入 BE 階段**: 批准 targeted 14B 降級與 action protocol 協定優化，無需先行優化防禦。

### BDE-Track 全庫能力發現與路徑相關性審計數據
1. **能力發現統計**:
   - **全庫 Canonical 能力數**: 34 個。
   - **BDC 覆蓋率與差異**: 23 個核心能力完全 active 覆蓋；其餘 11 個能力皆被正確判定為 out-of-scope（例如學術引用治理 `research_and_source_discipline`、外置生產力 `external_productivity`）。
   - **核心路徑 Blocker 缺失**: 0 個。
2. **失敗任務影響評估**:
   - 11 個失敗任務中無任何 P0/P1 能力缺口。
   - 缺失或未激活外圍能力對失敗任務解決率的影響為 **NONE**。
3. **最終審計決策**:
   - **最終決策 (verdict)**: `BDE8_NO_MISSED_REPAIR_RELEVANT_CAPABILITIES_PROCEED_BE` 結合 `BDE8_BD_CEILING_REMAINS_LOCAL_HEAL_FULL_ARMOR`。
   - **批准進入 BE 階段**: 全量核心防具極限 24/35 獲得證實，批准直接前進至 BE。

### 系統健康性
- 本地 343 個單元測試 100% 保持 PASS。
- 治理 flags 正確封鎖：`public_claim_allowed=false`, `production_ready=false`, `training_export_allowed=false`, `internal_only=true`。
