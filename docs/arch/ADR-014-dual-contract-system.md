# ADR-014: Dual Contract System — core/ vs engine/

**日期**: 2026-07-07
**狀態**: Accepted
**決策者**: C6AG Sprint

---

## 背景

Nexus 有兩套合約系統並存：

| 層級 | 路徑 | 用途 | 行數 |
|---|---|---|---|
| `nexus/core/` | SPXDRAC 原生合約 | 新架構，10 個模組 | ~500 行 |
| `nexus/engine/` | CapabilityPlanner runtime | production 工作馬 | ~1380 行 |

兩套系統各自定義 `CapabilityReceipt`、`SkillReceipt`、`CapabilityExecutionPlan`、`CapabilitySignalSet`、`CapabilityConstraints` 等型別，但欄位不相容。

## 問題

1. `engine/capability_contracts` 被 **17 個 production files** 引用
2. `core/belief_contracts` 只被 **7 個** 引用
3. `CapabilitySignalSet`：core 版 7 fields，engine 版 50+ fields
4. 兩套 `CapabilityReceipt` 的 claim verification logic 不同
5. 移除 engine bridge 會破裂 17+ production files + 30+ test files + 20+ adapter classes

## 決策

**不做型別統一。採取 bridge inline + 文件化策略。**

### 理由

| 因素 | 判斷 |
|---|---|
| 風險 | 型別統一會破裂 17+ production files |
| 收益 | 當前功能不受影響，兩套合約各司其職 |
| 維護成本 | bridge 只有 2 個 caller，可接受 |

### 實施

1. **C6AG bridge inline**（commit `0a16d3f38`）：`capability_selector.py` 的 34 行 bridge 已 inline 到 `capability_router.py`
2. **標記角色**：
   - `core/belief_contracts` = **SPXDRAC 契約**（新架構，用於 selector/router）
   - `engine/capability_contracts` = **runtime 工作馬**（production，用於 planner/executor）

## 架構圖

```
nexus/core/                          nexus/engine/
├── belief_contracts.py              ├── capability_contracts.py
│   ├── CapabilityReceipt            │   ├── CapabilityReceipt
│   ├── SkillReceipt                 │   ├── SkillReceipt
│   ├── CapabilityExecutionPlan      │   ├── CapabilityExecutionPlan
│   └── SkillSlot                    │   ├── CapabilitySignalSet (50+ fields)
│                                    │   └── CapabilityConstraints
├── capability_selector.py           │
├── capability_signal_set.py         ├── capability_planner.py (1380 行)
├── capability_constraints.py        ├── capability_router.py
└── executor_controls.py             └── capability_adapter.py

     ↓ SPXDRAC selector                    ↓ Production planner
     ↓ (7 files引用)                       ↓ (17 files引用)
     ↓                                     ↓
     └──────── bridge inline ──────────────┘
              (capability_router.py)
```

## 各自職責

| 合約系統 | 職責 | 主要 consumer |
|---|---|---|
| `core/belief_contracts` | SPXDRAC 七階段選擇、學習閉環、抗幻覺 | `CapabilitySelector`、`SkillsRouter` |
| `engine/capability_contracts` | runtime 路由決策、委員會執行、telemetry | `CapabilityPlanner`、`LocalModelExecutor`、`CommitteeOrchestrator` |

## 後續選項

| 選項 | 時機 | 風險 |
|---|---|---|
| 維持現狀 | 當前 | 低（兩套各司其職） |
| 逐步遷移 | 未來重構時 | 中（需逐個 file 更新 import） |
| 全面統一 | 不建議 | 高（破裂 17+ production files） |

## 結論

**兩套合約並存是刻意的架構決策，不是技術債。** `core/` 是未來方向，`engine/` 是當前生產力。bridge inline 確保兩者可以共存，不需要強制統一。
