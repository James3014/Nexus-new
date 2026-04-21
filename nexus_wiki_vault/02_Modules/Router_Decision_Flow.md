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
本頁解析 Nexus `SkillsRouter` 的決策邏輯，詳述其如何結合「領地防火牆」、「計費閘道」與「MSA 雙模檢索」來引導 Agent 任務。

## ⚙️ 決策流程 (The Routing Process)

### Step 1: 倫理與美學預審 (Critique Prescan)
- 調用 `CritiqueEngine` 掃描查詢語句，阻斷「反合理化」行為。

### Step 2: 計費與訂閱核驗 (Billing Check)
- 透過 `nexus/services/billing_engine.py` 確認租戶狀態。
- 狀態非 `active` 則回傳 `BLOCKED`。

### Step 3: 領地授權 (Firewall Authorization)
- 鑑定當前 `active_domain` (如 Q1_Critical_Core)。
- 物理阻斷非該領地允許的技能調用。

### Step 4: 雙模檢索 (Dual-Mode Search)
- **Palace Search (Tier 0)**: 優先搜尋 `memory_index.lancedb` 中的硬性規約。若 `hit_rate >= 0.8` 則直接採納。
- **MSA Semantic Search (Tier 1)**: 若 Palace 未命中，啟動全量向量檢索。

## 🛡️ 實體合約 (Input/Output Contract)
- **Input**: `query`, `tenant_id`, `active_domain`, `mode`.
- **Output**: `status`, `mode_used`, `results[]`, `p_phase`.

---
**[Source: nexus/core/router.py]**
