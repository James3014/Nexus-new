---
id: nexus_v24_hardening_crystal
type: spec
status: active
version: v24.1
---

# 🛡️ Nexus v24.1 治理硬化：水晶協議 (Hardening Crystal)

## 1. 核心硬化階段 (Stages A-G)
系統已完成以下物理硬化，確保交付路徑不可竄改且 Fail-Closed：

- **Stage A (Baseline Contract)**: 統一基線路徑於 `.nexus/reports/baseline/`，強化 Schema 雜湊鎖定。
- **Stage B (Replay Hard Fail)**: 無 `test_artifacts` 證據時，回放引擎強制攔截，拒絕 PASS。
- **Stage C (Lineage Chain)**: 建立 `lineage_chain.jsonl`，基於雜湊鏈防止歷史記錄靜默竄改。
- **Stage D (Regression Metrics)**: 回歸判定由「旗標式」升級為「指標式」，對比最近 N 次數據。
- **Stage E (Immutable Root)**: 鎖定核心治理腳本（`diagnose_regression.py` 等），偵測到漂移則自動報廢交付。
- **Stage F (Canonical Flow)**: 固化單一交付路徑：Dual-SHA -> Integrity -> Anti-Drift -> Lineage -> Replay -> Tests -> Regression -> Acceptance。
- **Stage G (Qualification Suite)**: 通過 10 任務（含 5 個對抗性攻擊）的資格認證。

## 2. 交付政策 (NEXUS_ACCEPTANCE_POLICY)

| 模式 | 描述 | 行為 |
| :--- | :--- | :--- |
| **DEV** | 開發引導模式 | 允許 `UNVERIFIED_COLD_START` 狀態，支援引導，不強制阻塞。 |
| **PROD** | 生產嚴格模式 | 嚴格執行 Fail-Closed。若觸發 **Code 16**，必須附帶 `CODE16_ROOT_CAUSE` 證據。 |

## 3. Code 16 故障排除協議
若交付門禁返回 Code 16，嚴禁重複空跑。必須執行：
1. 讀取 `.nexus/reports/acceptance_check.json`。
2. 提取 `CODE16_ROOT_CAUSE`（例如 `phantom_false_positive_rate:UNVERIFIED`）。
3. 針對性補充指標數據或修復邏輯。

---
[Governance Overview](../00_Home/System Overview.md)
