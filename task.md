# 🛡️ Nexus Master Taskboard: Surgical Intelligence (v1.0)

## 📋 任務清單 (TODO)

### [P1] 模組化基礎
- [ ] **T1.1**: 實作 `SurgicalRetriever` (職責：檔案粗定位)
- [ ] **T1.2**: 實作 `SurgicalSlicer` (職責：函式級精準切片)
- [ ] **T1.3**: 實作 `SurgicalPacker` (職責：預算動態封裝)

### [P2] TDD 驗證
- [x] TDD: 新增/更新 unit tests (7 new tests)
- [x] 全量 `pytest tests/unit/local_heal/` 無 regression — **23/23 PASSED**
- [x] 本地 Ollama qwen2.5-coder:7b 端到端驗證 `astropy-14096` — **Status: SUCCESS**
  - 成功定位 `__getattr__` property shadow 的根源
  - 透過 refined guidance 導引 7B 模型生成無 regression 的完美 descriptor check 補丁
  - 通過 `verify_bug_14096.py` 的閉環測試驗證astropy-12907 測試案例)
- [ ] **T2.2**: 撰寫 `tests/unit/test_surgical_packer.py` (驗證純淨代碼產出)

### [P3] 系統集成
- [ ] **T3.1**: 重構 `Localizer` Facade
- [ ] **T3.2**: 執行 `astropy-12907` 最終挑戰

### [P4] AS-R Milestones
- [x] Milestone AS-R1: Task Pack Manifest Reconstruction
  - [x] 實作 rebuild_asr_ceiling_benchmark.py 的 AS-R1 部分，分析 35 vs 29 mismatch
  - [x] 產出 task_pack_manifest.json (記錄 29 個任務，列出 6 個遺漏 task ids)
- [x] Milestone AS-R2: Per-Task Trace Emission
  - [x] 實作 trace 產生邏輯，在 rebuild_asr_ceiling_benchmark.py 中為 29 個任務產生 traces/<task_id>.json
- [x] Milestone AS-R3: Receipt and Claim Evidence Auditing
  - [x] 實作 receipt 產生與真實性稽核邏輯
  - [x] 執行實體回歸測試 (run_c12481_regression.py, run_c13453_regression.py) 並從中解析測試次數，將結果寫入 receipts
  - [x] 為其餘 27 個任務產生 skipped/unverified 且 tests_executed=0 的 receipts
- [x] Milestone AS-R4: Learning Closure Logging
  - [x] 實作 learning closure 與 summary 產出邏輯，只為通過之任務寫入日誌，其餘標明 skipped 原因
- [x] Milestone AS-R5: Rerun Auditable Ceiling Benchmark
  - [x] 執行單元測試 pytest，重跑基準測試
  - [x] 產出 asr_auditable_post_wiring_ceiling_v0/ 目錄下 10 大稽核與分析 json 檔，解決率分母為 29
- [x] Milestone AS-R6: Final Auditable Decision Report
  - [x] 產出決策報告 docs/reports/asr_auditable_post_wiring_ceiling_benchmark_v0.md (決策為 ASR6_TASK_PACK_REDUCED_RESULT_ONLY)
  - [x] 確保 local_heal 所有 304 個單元測試 PASS
  - [x] 更新 walkthrough.md
  - [x] git commit 結算變更，commit msg: "bench(local_heal): rebuild auditable post-wiring ceiling benchmark"

[NEXUS STATUS: SURGICAL_INTEL_INITIATED]

### [P5] AV-Track Milestones
- [x] Milestone AV1: Commit AS-R and Baseline Snapshot
  - [x] Git commit AS-R 變更 (已完成)
  - [x] 產出 asr_baseline_snapshot.json
- [x] Milestone AV2: Automatic Task Executability Inventory
  - [x] 實作排查與分類 21 個 skipped automatic 任務的 blocker 原因
  - [x] 產出 automatic_task_executability_inventory.json
- [x] Milestone AV3: Restore Safely Restorable Entrypoints
  - [x] 篩選並實施安全 entrypoints 復原與 Wrapper 修復
  - [x] 確保每個被復原之 entrypoints 產出規範的 trace/receipt json
  - [x] 產出 restored_entrypoints.json
- [x] Milestone AV4: Build Executable Automatic Subset
  - [x] 篩選並產出 executable_automatic_subset_manifest.json 與 excluded_automatic_tasks.json
- [x] Milestone AV5: Rerun Regression Health on Executable Subset
  - [x] 執行全量 unit pytest
  - [x] 執行被復原的 entrypoints，產出實體驗證成果與總計的 regression_summary.json
- [x] Milestone AV6: Determine Whether Ceiling Benchmark Can Resume
  - [x] 根據 meaningful 規則產出 ceiling_readiness_decision.json
- [x] Milestone AV7: Final Direction Decision
  - [x] 產出報告 docs/reports/av_executable_benchmark_substrate_restoration_v0.md
  - [x] 確保 unit tests 保持 PASS
  - [x] 更新 walkthrough.md
  - [x] git commit 結算變更，commit msg: "bench(local_heal): restore executable benchmark substrate"

