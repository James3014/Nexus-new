---
title: Source - Coverage Heatmap
aliases: [Wiki Coverage, Documentation Heatmap]
type: sources
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: .nexus/reports/wiki_coverage_report.json
related_pages:
  - "[[Source Index]]"
  - "[[System Overview]]"
  - "[[Ops - Wiki Drift Audit]]"
tags: [sources, coverage, audit, heatmap]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Source - Coverage Heatmap

## One-sentence summary
本頁展示 Nexus 核心程式碼在治理 Wiki 中的覆蓋率分佈情況。 [Source: scripts/ops/wiki_coverage_audit.py]

## Role / responsibility
- **透明度管控**: 提供量化指標，識別哪些實體檔案目前處於「治理真空」或「未被 Wiki 描述」狀態。 [Source: .nexus/reports/wiki_coverage_report.json]
- **優先級導航**: 引導治理工程師優先補齊高風險、未覆蓋的代碼路徑文檔。

## Current Coverage Ratio (當前覆蓋率)

> [!NOTE]
> **Coverage Ratio: 63.53%**
> 計算基準：`nexus/core`, `nexus/services`, `scripts/ops`, `scripts/engine` 內檔案總數對比 Wiki [Source:] 引用數。

### Summary Metrics
- **Total Code Files**: 255 [Source: scripts/ops/wiki_coverage_audit.py]
- **Covered Files**: 162
- **Uncovered Files**: 93
- **Stale Coverage**: 待 Audit (參見 [[Ops - Wiki Drift Audit]])

## Top 20 Uncovered Files (治理缺口)

| Path | Risk (Estimated) | Reason |
|---|---|---|
| `scripts/engine/l6_gate.py` | High | 缺乏對 L6 Gate 的治理描述。 |
| `scripts/engine/ci_graph_impact.py` | High | 圖譜影響力分析未納入規範。 |
| `scripts/engine/nexus_transaction.py` | Mid | 事務處理邏輯未對位。 |
| `scripts/engine/speculative_hooks.py` | Low | 投機 Hook 屬於實驗性功能。 |
| `scripts/engine/critique_engine.py` | Mid | 稽核引擎實作。 |
| `scripts/engine/node_launcher.py` | Mid | 節點啟動邏輯。 |
| `scripts/engine/intent_classifier.py` | Mid | 意圖分類邏輯。 |
| `scripts/engine/nx_impact.py` | Mid | 影響力分析腳本。 |
| `scripts/engine/ci_fix_generator.py` | Mid | CI 修復產出器。 |
| `scripts/engine/hybrid_patcher.py` | Mid | 混合補丁。 |

## Upstream
- **Wiki Audit Engine**: `scripts/ops/wiki_coverage_audit.py` [Code: scripts/ops/wiki_coverage_audit.py]
- **Provenance Tags**: 全庫 `[Source: path]` 標籤。

## Downstream
- **[[Source Index]]**: 提供全域來源索引。
- **[[Ops - Wiki Drift Audit]]**: 驗證已覆蓋項的時效性。

## Related modules / files
- `.nexus/reports/wiki_coverage_report.json`: 生成的報表。 [Source: .nexus/reports/wiki_coverage_report.json]

## Source notes
- v22 Engine Spec: 要求所有核心服務 (`nexus/services`) 必須具備 1:1 的治理對應關係。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Dynamic Paths**: 如何處理 `*.so` 或二進位檔案的覆蓋率標記。
- [ ] **Exclusion List**: 是否應排除 `__init__.py` 等結構性檔案以優化指標。
