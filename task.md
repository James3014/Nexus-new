# Nexus 自動化與數據真相 (Automation & Truth Protocol)

## 🎯 目標
將 Nexus 治理從「文件結案」升級為「數據驅動的自動化防線」，確保所有指標可透過實測數據（Tokens, Drift, Pass/Fail）證偽。

## Track H：數據真相 (Truth Dashboard) [x]
- [x] **TRU-101 真實 Token 追蹤**: 正則表達式邏輯已通過單元測試，集成環境測試已觸發並驗證。
- [x] **TRU-102 數據真相儀表板**: 自動產出 `nexus_truth_dashboard.md` 並落地專案根目錄。
- [x] **Task 3: `hidden_bugfix_supervised` background offload 實驗 (優先級: P1)**
  - [x] 執行 background replay 與 longer-timeout lane 隔離實驗
  - [x] 補測試：驗證 heavy rows 可移出主線，主 runner 不因單一 flaky row 發生長時間阻塞
  - [x] **狀態**: `COMPLETED`。已成功實作 `--enable-background-offload` 與 `--heavy-task-ids` 支援背景非阻塞隔離執行，並通過 TDD 測試。*註：Task 3 目前屬 observation-only / experimental runner path，僅驗證 heavy rows 可被背景隔離且不阻塞主流程；不構成 public claim、promotion evidence、或 audited final bundle 替代品。*
- [x] **Dual-Engine Phase 2: Data Loop Hardening**
  - [x] **Phase A: 穿甲核心具現化 (Armor Core)**
  - [x] `[NEW]` 具現 `nexus/core/subagent_armor.py`
  - [x] `[MODIFY]` 注入 `scripts/engine/nexus_cli.py` (`nexus:runner` 與 `_enforce_armor`)
  - [x] `[NEW]` 具現 `tests/governance/test_subagent_armor.py`

- [x] **P3: Evidence-plane Consume 與可重放證據 Artifact**
  - [x] 撰寫 `test_governance_telemetry_closure.py` 中的實體可重放測試案例（紅燈）
  - [x] 升級 `DualGateVerifier.verify_receipt`，強制產生包含 `repro_command`、`timeout_sec`、`cwd`、`pass_fail_evidence` 的 JSON 實體證據檔案
  - [x] 在 `.nexus/reports/` 目錄下流式寫入 `.json` 證據包，將其路徑回傳給 `evidence_bundle`
  - [x] 驗證並通過 P3 測試案例（綠燈）

- [x] **P4: Sanitized Runner 的 UV 快取隔離與權限防禦**
  - [x] 撰寫 `test_uv_cache_isolation.py` 快取與權限異常防禦測試案例（紅燈）
  - [x] 修改 `AsyncProcessExecutor.run_async` 異步啟動時，自動注入 `UV_CACHE_DIR` 獨立環境變數至 workspace `.tmp/uv-cache`
  - [x] 對 `PermissionError` 進行安全捕獲、日誌自癒報警與 fallback 降級處理
  - [x] 驗證並通過 P4 測試案例（綠燈）

- [x] **P5: Eligibility Completeness 與 Telemetry 遙測收口**
  - [x] 撰寫預期 expected receipts 遙測與 eligibility 完整性測試（紅燈）
  - [x] 升級 core/engine 的 `CapabilityReceipt` schema 欄位，新增 `telemetries`，更新 `is_claimable` 與 `public_claim_safe` 遙測限制門檻
  - [x] 將遙測寫入 beliefs / closeout 合約，確保 promotion 流程完全對齊
  - [x] 驗證並通過 P5 測試案例（綠燈）

- [x] **Phase B: 物理鏈集成 (Chain Integration)**
  - [x] `[MODIFY]` 注入 `scripts/core/parallel_spawner.py` (盔甲注入、Handoff 協議、超時回滾)
  - [x] `[MODIFY]` 注入 `nexus/engine/phases/repair.py` (分身 JSON 回傳模式)
  - [x] `[MODIFY]` 注入 `nexus/engine/coordinator.py` (收攏結果與知識結晶化)

- [x] **Phase C: 終極驗收 (Verification)**
  - [x] `[RUN]` 執行 `pytest tests/governance/test_subagent_armor.py`
  - [x] `[RUN]` 執行 `nexus_cli.py nexus:status --aos-full`
  - [x] `[DOC]` 產出 Walkthrough 分身治理結報
雙子星報告
- [x] **P11.1 環境清場與基建 (Infrastructure)**
    - [x] `minikube delete --all --purge`
    - [x] `brew install minikube kubectl helm`
    - [x] `minikube start --nodes 5 --cpus 2 --memory 4096 --driver=docker`
- [x] **P11.2 鏡像構建與模型密封 (Dockerfile)**
    - [x] `docker build -t nexus:v18.4-ollama .` (密封 Llama 3.1)
    - [x] `minikube image load nexus:v18.4-ollama`
- [x] **P11.3 Swarm 集群佈署 (Deployment)**
    - [x] `helm install nexus-swarm ./nexus-chart --namespace nexus --create-namespace`
    - [x] `kubectl scale deployment nexus-swarm -n nexus --replicas=10`
- [x] **P11.4 200 併發基準測試 (Benchmark)**
    - [x] `benchmark_suite.py --k8s --tasks=200 --concurrency=20 --per-pod-limit=2`
- [x] **P11.5 最終認證與回報 (Certification)**
    - [x] 提取 `p11_swarm.log` 指標
    - [x] 完成 v18.4 正式晉升對位

## Track I：自動化回歸 (CI & Pytest) [x]
- [x] **AUT-101 Pytest 規格化**: 重構 `tests/test_v9_regression_p1.py`。
- [x] **AUT-102 CI Lane 實作**: 建立 `scripts/ci_gate.py` 無捲標自動化測試流。
- [x] **AUT-103 測試補全**: 建立 `tests/test_llm_token_regex.py` 參數化驗證證據。

## Track J：案例擴展 (Case Expansion) [x]
- [x] **EXP-001 案例補齊至 10 個**: 覆蓋 Bug/Feature/DI/Fast/Audit 等情境。
- [x] **EXP-002 批量 Replay 驗證**: 確保 10 個案例全數可跑且結果一致。

---
## Track K：難題 Wall Time & Token 底層物理優化 (Hardcore Physical Optimization)
- [x] **PHY-101 增量 AST 圖掃描**
- [x] **PHY-102 動態測試程式碼裁剪**
- [x] **PHY-103 預設 Compact 模式**
- [x] **PHY-104 實體連網 A/B 評測與數據對決**

---
**核准狀態：Active Aligned (REALISM_S10 Certified)**


