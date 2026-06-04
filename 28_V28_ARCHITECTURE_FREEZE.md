# ❄️ v28 Architecture Freeze (Operational Baseline)

## 📌 核心狀態
**架構狀態：FROZEN**
**版本範疇：v28.1 - v28.2**

---

## 🏛️ 模組邊界規約 (Boundary Contracts)

本文件宣告以下四個核心模組的公共介面進入 **Stable** 狀態。任何違反邊界的越位調用將被 `FitnessGate` 物理攔截。

### 1. 狀態層 (`nexus.state.task_state_store`)
- **角色**：唯一真實狀態來源 (SSoT)。
- **核心介面**：
    - `get_latest(task_id)`: 獲取最新版本狀態。
    - `commit(task_id, payload)`: 提交新版本，自動處理版本遞增。
    - `rollback(task_id, to_version)`: 安全回滾至指定版本。
- **邊界禁令**：不得依賴任何判決器或執行車道細節。

### 2. 遙測層 (`nexus.telemetry.telemetry_models`)
- **角色**：收集指標 Facts。
- **核心介面**：
    - `TelemetryBundle`: 包含 `wall_time_ms`, `token_usage`, `provider_costs`, `overhead_ms`。
    - `complete` 屬性：物理判定指標是否收集齊全。
- **邊界禁令**：不得包含任何政策判決邏輯。

### 3. 檢索層 (`nexus.memory.memory_retrieval_service`)
- **角色**：因果權重檢索。
- **核心介面**：
    - `rank_and_pack(hits, state_version)`: 執行分層排序與版本過濾。
- **不變量**：排序權重固定為 `Failure Signature > Family > Archive`。
- **邊界禁令**：不得直接改動 `GateJudge` 的允許狀態。

### 4. 判決層 (`nexus.gate.gate_judge`)
- **角色**：純函數判決器。
- **核心介面**：
    - `decide(ticket, replay, telemetry, seal)`: 產出不可變判決收據。
- **不變量**：相同輸入必得相同判決。
- **邊界禁令**：禁止執行 I/O 或自行補齊數據。

---

## 🛠️ 遷移與回歸 (Migration & Regression)
- 舊版 v27/v28.0 數據必須通過 `BackfillService` 對齊上述契約。
- 缺失指標統一標記為 `BACKFILL_NEEDED`，嚴禁虛假晉升。
- **回歸基線**：已固化於 `docs/governance/v28.2_REGRESSION_BASELINE.md`。

---

## 🏁 最終判定
**v28.2 OPERATIONAL STATUS: STABLE BASELINE**
**驗證證據**：39 verified contract/integration tests passed.
**限制**：僅允許新增測試以強化邊界，嚴禁未經 RFC 變更四層核心合約。

---
[SSOT: V28_ARCHITECTURE_FREEZE_MANIFEST]
