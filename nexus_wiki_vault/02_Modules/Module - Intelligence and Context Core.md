---
aliases:
- Context Hub
- RAG Core
- Brain Intelligence
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[Module - Memory Pipeline Deep Dive](Module - Memory Pipeline Deep Dive.md)'
- '[Module - Implementation Responsibility
  Matrix](Module - Implementation Responsibility Matrix.md)'
- '[Module - Skill Memory Closed Loop](Module - Skill Memory Closed Loop.md)'
source_of_truth: nexus/core/context_hub.py
status: active
tags:
- core
- intel
- context
- rag
- crystal
- brain
title: Module - Intelligence and Context Core
type: module
version_scope:
- v22
- v23
---



# Module - Intelligence and Context Core

## One-sentence summary
本模組集合了 Nexus 的語義上下文管理、RAG 向量檢索、模型自省邏輯與知識「晶體」(Crystal) 的生命週期管理。 [Source: nexus/core/context_hub.py]

## Role / responsibility
- **語義路由**: 透過 `Context Hub` 將任務目標分發至最佳的 RAG 召回路徑。
- **知識固化**: 驅動 `Crystal Analyzer` 從執行證據中提取可重複使用的 Pattern。
- **上下文協調**: 在多模型 (Gemini/GStack) 切換時確保護欄與變量的一致性。

## Intelligence Component Registry (智慧組件登記)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Context Hub** | Agent 運行時上下文的中心分發器。 | [Source: nexus/core/context_hub.py] |
| **Context Compression** | 壓縮長上下文以節省 Token。 | [Source: nexus/core/context_compression.py] |
| **Vector RAG** | 基於向量庫的語義召回邏輯。 | [Source: nexus/core/vector_rag.py] |
| **Crystal Node** | 知識「晶體」數據結構定義。 | [Source: nexus/core/crystal.py] |
| **Crystal Analyzer** | 分析並歸納任務中的 Pattern 與 Lessons。 | [Source: nexus/core/crystal_analyzer.py] |
| **Brain Intelligence** | 模型能力預測與多模型路由邏輯。 | [Source: nexus/core/commander.py] |
| **Ink Parser** | 分析與解析 Markdown/JSONL 中的語義塊。 | [Source: nexus/core/ink_parser.py] |
| **[[SKILL]] Distiller** | 從歷史執行中蒸餾出高可用 [[SKILL]] 清單。 | [Source: nexus/core/skill_distiller.py] |
| **[[SKILL]] Compressor** | [[SKILL]] 定義的長度壓縮與 Token 優化。 | [Source: nexus/core/skill_compressor.py] |
| **[[SKILL]] Outcomes** | [[SKILL]] 執行的結果分類與預測。 | [Source: nexus/core/skill_outcomes.py] |
| **Neural Aggregator** | 多路神經網路結果彙整與共識達成。 | [Source: nexus/core/neural_aggregator.py] |
| **Gemini Handoff** | 多模型間的狀態移送與上下文對齊。 | [Source: nexus/core/gemini_handoff.py] |
| **Handoff Builder** | 構建模型間移交的物理數據封裝。 | [Source: nexus/core/handoff_builder.py] |
| **Handoff Bundle** | 包含完整上下文與資源權限的移交包。 | [Source: nexus/core/handoff_bundle.py] |
| **[[BELIEF]] Engine** | 信念修正引擎，管理 Wisdom Prior 與 Router Bias。 | [Source: nexus/services/mem_palace.py] |
| **OutputGuard** | **[NEW] Context Shield**：物理日誌截斷與上下文護欄。 | [Source: scripts/engine/output_guard.py] |

## Belief Revision System (信念修正系統 v0.9)

Nexus 採用 **Belief Revision** 框架來處理隨著時間與證據演進的「動態事實」。這使 Agent 具備「撤回過時判定」與「根據新證據修正偏置」的能力。

### 核心定義 (Definitions)
- **[[BELIEF]]**: `Wisdom Prior` + `Router Bias` 的結合。
- **目的**: 將「記住舊資料」提升為「維護當前有效之判斷」。

### 演進軌跡 (Evolution Path)

| Version | Belief Dimension | Logic (邏輯) |
|---|---|---|
| **v0.7** | 8-dim | 靜態 `Prior` 硬編碼偏好。 |
| **v0.8** | 128-dim | 單機 `Meta-Optimizer` 回寫之 `dna_delta`。 |
| **v0.9** | **16-dim** | **聯邦智慧 (Federated Wisdom)** 基於 10 Tenants 聚合之 `global_router_bias`。 |

### 核心操作 (AGM Inspired)
- **Expansion (擴張)**: 納入新證據，生成新信念。
- **Revision (修正)**: 基於新證據修改舊有的 Wisdom Prior。
- **Contraction (撤回)**: 移除已判定為無效或衝突的 Belief，傳導影響至下游 Artifacts。

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 全域智慧架構導航。
- **MUSE-NEXUS Spec**: 定義知識提取 (Crystallize) 的邏輯標準。

## Downstream
- **[Module - Implementation Responsibility Matrix](Module - Implementation Responsibility Matrix.md)**: 智慧模組與物理檔案映射。
- **[Module - Memory Pipeline Deep Dive](Module - Memory Pipeline Deep Dive.md)**: 技術細節實作對接。
- **[Module - Skill Memory Closed Loop](Module - Skill Memory Closed Loop.md)**: Belief 信念如何透過 ContextHub 過濾技能並回寫路由器偏誤 (Phase 13)。

## Related modules / files
- `nexus/core/context_hub.py`: 上下文樞紐。 [Code: nexus/core/context_hub.py]
- `nexus/core/crystal.py`: 知識晶體。 [Code: nexus/core/crystal.py]
- `nexus/core/vector_rag.py`: RAG 引擎。 [Code: nexus/core/vector_rag.py]
- `scripts/engine/output_guard.py`: 物理上下文護欄。

## Source notes
- v22 Engine Spec: 要求 RAG 召回精度 (Precision@3) 必須 > 0.85 以避免幻覺。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Embedding Drift**: 隨著模型更新，如何自動偵測並重新索引各項晶體。

---
Back to [System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]