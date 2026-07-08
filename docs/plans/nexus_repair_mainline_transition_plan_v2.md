# Nexus Repair Mainline Transition Plan v2

> 目標：把 Nexus 從「多模型實驗堆疊」整理成「模型提案、Nexus 理解、Nexus 驗證、Nexus 決策」的修復系統。
>
> **核心策略：Top-down enforcement。先設柵欄再補資料管線。**
> 每一步都必須改變系統行為，不允許只加欄位不加 enforcement。

## 已完成

- P0: dirty tree 分類 ✅
- P0.5: needs_recheck 拆分 ✅
- P1: `CanonicalPatchCandidate` + `OutputUnderstandingResult` + executor adoption + candidate projection ✅
- P1.5: `protocol.py.classify_format()` 收斂到 `output_understanding._detect_format()` ✅
- P2: Apply / Hash / Anchor Truth（7 subtasks 全數通過）✅
- 4 pre-existing collection errors 修復（committee import + rank_bm25）✅
- 7 pre-existing test failures 修復（P2 regression + failure_class + parser API）✅

## P2: Apply / Hash / Anchor Truth ✅

### 策略

**先 enforcement（gate），再生產者（producer），最後舊版路徑（committee）。**

P2 所有子任務都必須在 ship 後改變系統行為。禁止純 schema/欄位/資料傳遞的任務。

| 標籤 | 內容 | 狀態 |
|------|------|------|
| P2-1 | Anchor fields 加到 `CanonicalPatchCandidate` + executor enrichment | ✅ c5220fe75 |
| P2-2 | Propagate anchor fields 透過 executor meta 到 receipt | ✅ af9686b5a |
| P2-3 | Anchor fields 加到 `CandidateIsolationReceipt` + blocker | ✅ ed50cbf5e |
| P2-C | `candidate_hash_matches_applied` consumer 在 claim gate | ✅ 9eda9d8da |
| P2-D | Producer bridge executor → orchestrator validate_context | ✅ 2d998aae2 |
| P2-E | Target file presence check 在 claim gate | ✅ 8715759e3 |
| P2-F | Committee path hash_match 寫 route_context | ✅ 8715759e3 |

### 關鍵規則（已實現）

- `candidate_hash_matches_applied == false` → `claim_gate_passed = false`
- `source_hash present + no candidate_target_file` → `claim_gate_passed = false`
- committee 路徑和 pipeline 路徑都走同一個 gate
- 執行路徑已補上 `candidate_target_file` 傳遞（isolated_local_solve_loop + local_solve_dry_run_loop）

## P3: Signal → Execution Topology Data Flow Audit（🟡 可執行，唯讀 only）

> **MCP 裁決**：P3 可以開始，但只能開始唯讀 audit。
> P3 implementation（router / cloud_with_local_assist / quota / diversity committee）不可開始。
> 條件：P2 apply truth 已穩定，但 executor delegated retry / committee 路徑仍有紅燈（2026-07-08 修復前 24 failed，修復後 0 failed 但仍需 MCP 確認）。

### 現狀

P2 已完成。P3 目前 scope = **唯讀 audit**，禁止任何實作變更。

### Scope ✅（可做）

- 只讀追蹤 `signal_snapshot` / `execution_topology` / `route_context` 資料流
- 必查：
  - `nexus/engine/capability_planner.py`
  - `nexus/services/local_heal/capability_adapter.py`
  - `nexus/services/local_heal/local_model_executor.py`
  - `nexus/services/local_heal/local_model_capability_context.py`
  - `nexus/services/local_heal/local_committee_candidate_provider.py`
  - `nexus/services/local_heal/claim_delivery_gate.py`
  - `tests/unit/local_heal/test_capability_adapter.py`
  - `tests/unit/local_heal/test_local_model_executor.py`
  - `tests/benchmark/test_local_model_executor_planner_path.py`

### Scope 🛑（不可做）

- 不改 `router.py`
- 不改 `capability_planner.py`（唯讀可讀，不可改）
- 不新增 route / enum / adapter
- 不接 cloud endpoint
- 不做 quota tracker
- 不做 diversity committee
- 不宣稱 cloud_with_local_assist ready

### Deliverable

`docs/reports/p3_signal_execution_topology_dataflow.md`，必須包含：

1. **signal_snapshot schema registry** — 每個欄位的型別、預設值、來源層
2. **producer → consumer mapping** — 每個欄位從哪個模組寫入、哪個模組讀取
3. **execution_topology 回流到 receipt 的路徑** — topology 如何從 executor → receipt
4. **P2 修復後殘留斷點歸因** — signal 是否仍有未正確往下傳的欄位
5. **rank_bm25 dependency 判斷** — 是否應變成 optional / fallback / test fixture mock
6. **P3 實作前 unblock checklist** — 列出 audit 後 required 的修復項目

### P3 實作前 Unblock Checklist（預期由 audit 產出）

- [ ] executor delegated retry / committee metadata 全綠（已修復，待穩定觀察）
- [ ] signal_snapshot 所有欄位 producer → consumer 完整 traceable
- [ ] route_context 所有欄位在關鍵路徑上正確傳遞
- [ ] rank_bm25 依賴決策完成（optional / mock / keep）
- [ ] P3 implementation risk assessment 完成

## P4 / P5 / P6：全部保留為後續

P4（diversity committee）的啟用條件依賴 P3 狀態機。P5（committee 定型）依賴 P4。P6（quota-aware）依賴 P3 routing tree。P2 完成前不碰這些。

## 驗收標準

任何 package ship 時必須回答：
1. 系統行為改變了什麼？
2. 測試怎麼證明行為改變？
3. 有沒有純資料不動行為的變更？（禁止）

## 不允許的宣稱（永遠）

- `public_claim_allowed` 永遠 false
- `production_ready` 永遠 false
- 不可宣稱 solve rate、production ready、local armor ready
- 只能宣稱 contract/pass/fail 與 hash/anchor evidence
