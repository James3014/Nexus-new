---
aliases: '[DeepScientist Integration, Research Engine, Bayesian Optimization]'
confidence: high
last_compiled: '2026-04-07'
owner: agent
status: active
tags: '[research, [[DEEPSCIENTIST|deepscientist]], autonomous, optimization]'
title: Research - DeepScientist Integration
type: research
---

# 🧬 Research - DeepScientist Integration (v22.2)

## One-sentence summary
定義 DeepScientist 自主研究框架在 Nexus 核心循環中的整合規範與貝葉斯優化協議。 [Source: nexus/research/]

## Role / responsibility
- **優化決策**: 提供 `BayesianResearchOptimizer` 進行超參數建議以驅動修復循環。 [Source: nexus/research/bayesian_engine.py]
- **經驗持久化**: 透過 `FindingsMemoryStore` 提供機器可讀、結構化的研究記憶卡。
- **軌跡視覺化**: 提供 Mermaid 基於權重與得分的研究演化圖譜。

## 🛠️ 核心指令 (DeepScientist CLI)
- `nexus:memory-list --scope [task|global]`: 列出結構化研究記憶卡 (`FindingsCard`)。
- `nexus:research-map --task-id <ID> --output <FILE.mmd>`: 生成研究演化地圖。
- `scripts/nightshift.py`: 啟動貝葉斯優化研究循環。

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 提供全域架構上下文。
- **[Module - Core Orchestrator](../02_Modules/Module - Core Orchestrator.md)**: 驅動 NightShift 循環的引擎。

## Downstream
- **[Ops - Governance Changelog](../06_Ops/Ops - Governance Changelog.md)**: 紀錄研究導致的治理變更。
- **.nexus/memory/**: 物理存儲輸出的研究結晶。

## Related modules / files
- `nexus/research/findings_memory.py`: 記憶卡管理核心。
- `nexus/research/bayesian_engine.py`: GP-EI 優化器。
- `nexus/research/research_map.py`: Mermaid 渲染器。

## Source notes
- v22.2 Patch: 實作 DeepScientist 原型到生產級的膠合轉換。

## Open questions / conflicts
- [ ] **Vector Search**: 未來是否將存儲路徑由 JSON 遷移至 LanceDB 全文本索引。

---
[[System Overview]]
