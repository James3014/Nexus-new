---
aliases: '[Router Flow, Strategy Routing, Memory Routing]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
source_of_truth: nexus/core/router.py
status: hardened
tags: '[core, architecture, router, flow]'
title: Module - Router Decision Flow
---

# Module - Router Decision Flow (v26 Hardened)

## One-sentence summary
本頁解析 `SkillsRouter` 的決策邏輯，描述其如何結合預審、授權與搜尋策略驅動路由決定。 [Source: nexus/core/router.py]

## Role / responsibility
- 定義路由決策流程與保護性檢查順序，確保每個任務都有可回放的流程邏輯。 [Source: nexus/core/router.py]
- 對上游 Orchestrator 提供模式切換與結果標註。 [Source: nexus/core/orchestrator.py]

## Upstream
- `nexus/core/orchestrator.py` 提供主循環節點與異常回退策略。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_contracts.py` 提供狀態欄位一致性。 [Source: nexus/core/state_contracts.py]

## Downstream
- `Module - Core Orchestrator` 使用本決策結果推進任務執行。 [Source: 02_Modules/Module - Core Orchestrator.md]
- 能力路由 smoke 以本頁規格為預期行為對照。 [Source: scripts/ops/capability_route_smoke.py]

## Related modules / files
- `nexus/core/router.py`: 路由核心實作。 [Source: nexus/core/router.py]
- `nexus/core/orchestrator.py`: 執行序列協調。 [Source: nexus/core/orchestrator.py]
- `nexus/services/context_crystal.py`: context 化輸入資料。 [Source: nexus/services/context_crystal.py]

## Source notes
- 本流程源於 `nexus/core/router.py` 的輸入輸出和路由分支實作。 [Source: nexus/core/router.py]

## Open questions / conflicts
- [ ] 是否要將計費與領地授權結果加入 evidence receipt 的必帶欄位。 [Source: nexus/core/router.py]

## ⚙️ 決策流程 (The Routing Process)

### Step 1: 倫理與美學預審 (Critique Prescan)
- 調用 `CritiqueEngine` 掃描查詢語句，阻斷「反合理化」行為。

### Step 2: 計費與訂閱核驗 (Billing Check)
- 透過 `nexus/services/billing_engine.py` 確認租戶狀態。
- 狀態非 `active` 則回傳 `BLOCKED`。

### Step 3: 領地授權 (Firewall Authorization)
- 鑑定當前 `active_domain`（如 `Q1_Critical_Core`）。
- 物理阻斷非該領地允許的技能調用。

### Step 4: 雙模檢索 (Dual-Mode Search)
- **Palace Search (Tier 0)**: 優先搜尋 `memory_index.lancedb` 中的硬性規約。若 `hit_rate >= 0.8` 則直接採納。
- **MSA Semantic Search (Tier 1)**: 若 Palace 未命中，啟動全量向量檢索。

## 🛡️ 實體合約 (Input/Output Contract)
- **Input**: `query`, `tenant_id`, `active_domain`, `mode`.
- **Output**: `status`, `mode_used`, `results[]`, `p_phase`.

---
**[Source: nexus/core/router.py]**

[[System Overview]]
