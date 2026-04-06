---
title: Module - Metadata Collectors
aliases: [Metadata Collectors, Data Sources]
type: module
status: proposed
version_scope: [v23]
source_of_truth: scripts/engine/collectors/node_collector_v1.py
raw_sources:
  - scripts/engine/collectors/node_collector_v1.py
  - scripts/engine/collectors/edge_resolver_v1.py
related_pages:
  - "[[Module - Core Orchestrator]]"
  - "[[Source Index]]"
tags: [module, metadata, collector, proposed]
last_compiled: 2026-04-06
confidence: low
owner: agent
---

# Module - Metadata Collectors

> [!WARNING]
> **Governance Conflict**: 根據 2026-04-06 審計結果，`node_collector_v1.py` 與 `edge_resolver_v1.py` 尚未在正式 `scripts/engine/` 目錄中物理落地。

## One-sentence summary
本模組提案負責 `MUSE_ENGINE` 數據層的節點與邊緣關係採集，目前作為治理藍圖進行記錄。 [Source: W-01-Proposed]

## Role / responsibility
- **節點自省**: 採集 Nexus 全量代碼與文檔節點的 Metadata。
- **關係解構**: 定義各組件間的邏輯依賴與物理鏈路。
- **數據彙編**: 生成用於治理的可機讀 `manifest.json` 與 `knowledge_graph` 對象。

## Upstream
- **MUSE Spec v23**: 定義對「全局 Metadata 實時一致性」的架構要求。
- **[[System Overview]]**: 系統導航。

## Downstream
- **[[Module - Core Orchestrator]]**: 調度器依賴此層數據進行任務分析（X 相位）。

## Related modules / files
- `scripts/engine/collectors/node_collector_v1.py` (Missing) [Source: [[System - Unknowns and Conflicts]]]
- `scripts/engine/collectors/edge_resolver_v1.py` (Missing) [Source: [[System - Unknowns and Conflicts]]]

## Source notes
- **Conflict Registry**: 物理對象缺失，列為 v23 首批補全對象。

## Open questions / conflicts
- [ ] **Physical Existence**: 檔案目前僅存在於臨時 Cache，需於 v23 正式版完成 `scripts/engine/` 的遷移落地。
- [ ] **Performance**: 對大體量 Repo 進行全量自省時的超時限制與分片邏輯。
