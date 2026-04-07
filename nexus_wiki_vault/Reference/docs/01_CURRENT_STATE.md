---
id: 01_current_state
type: doc
status: active
created: 2026-04-07T07:29:30Z
updated: 2026-04-07T07:29:30Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/docs/01_CURRENT_STATE.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---
# Muse-Nexus Current State

## Executive Summary

Muse-Nexus 現況不是完整的 workflow operating system，而是以本機腳本組成的 coding operations system。

它已經具備的核心能力：

- coding loop orchestration
- git / worktree isolation
- diagnosis and repair assist
- local memory retrieval from Obsidian + [[Module - Memory Repository|LanceDB]]
- audit / quality gate / dashboard tooling

它尚未具備的核心能力：

- 統一的 `.muse_state` state model
- Commander 作為單一正式 orchestrator
- [[Module - Intelligence and Context Core|Context Hub]] 作為獨立 context assembler
- 表驅動 skills router
- `plan.json` / `diagnosis.json` / `repair_final.json` / `audit_result.json` 等 contract

## Observed System Shape

```text
Intent
  -> codex_loop_brain
  -> workspace_manager / git_manager
  -> diagnosis / repair / audit scripts
  -> memory recall
  -> dashboard / state summary
```

## Major Capabilities Already Present

### 1. Coding Loop / Orchestration

Relevant files:

- `scripts/codex_loop_brain.py`
- `scripts/workspace_manager.py`
- `scripts/git_manager.py`

Current role:

- 執行 coding review / patch / retry loop
- 管理 worktree 隔離
- 讀 lessons / dynamic recall / drift guard

Assessment:

- 這是現況最接近「Commander 前身」的部分。
- 問題是 orchestration、context assembly、policy、repair loop 混在同一個大腳本裡。

### 2. Diagnosis

Relevant file:

- `scripts/drclaw_diagnosis.py`

Current role:

- 根據錯誤訊息、Codex report、本地 knowledge hit 產出 diagnosis 類結果
- 可透過 qmd 與 `brain_search_v2.py` 取得過往記憶

Assessment:

- 已有診斷引擎雛形
- 但輸出 schema 不穩定，還不是正式 `diagnosis.json` contract

### 3. Memory / Knowledge Layer

Relevant files:

- `scripts/brain_search_v2.py`
- `scripts/brain_search_v3.py`
- `scripts/brain_search_v4.py`
- `scripts/flash_ingest_v2.py`
- `scripts/brain_crystallizer_pro.py`

Current role:

- 將 Obsidian vault 內容向量化進 [[Module - Memory Repository|LanceDB]]
- 支援語義檢索、信號強度、部分時間權重與重排策略

Assessment:

- 這是目前最成熟、最接近平台級能力的一層
- 也是未來 [[Module - Intelligence and Context Core|Context Hub]] 的核心資料來源

### 4. Audit / Quality Control

Relevant files:

- `scripts/pre_write_quality_gate.py`
- `scripts/final_path_audit.py`
- `scripts/brain_semantic_audit.py`
- `scripts/ghost_audit.py`
- `scripts/identity_audit.py`

Current role:

- 執行寫入前檢查
- 執行特定型別的 audit / hygiene / semantic checks

Assessment:

- audit 能力已存在
- 但目前是多個分散工具，不是統一的 Audit engine

### 5. Dashboard / Operations Visibility

Relevant files:

- `scripts/app.py`
- `scripts/script_dashboard.py`
- `scripts/state_reconstructor.py`

Current role:

- 顯示 agent / events / scripts 狀態
- 將事件流重建成摘要型狀態檔

Assessment:

- 代表系統有 war room 思路
- 但目前觀測對象不是明確的 phase-[[Module - State Contracts|state contracts]]

## Current System Weaknesses

1. 大量責任堆在單一腳本中，尤其 `codex_loop_brain.py`
2. 缺少正式 [[Module - State Contracts|state contracts]]，導致 phase 邊界模糊
3. event / audit / reflection 資料沒有收斂到單一路徑
4. repo 內存在 duplicated / migrated 腳本，顯示邊界仍不乾淨
5. 缺少正式 [[README]] / docs / backlog，接手成本高

## Practical Conclusion

Muse-Nexus 現在的真實定位是：

> 一套面向寫 code、修 code、審 code 的本機腳本化作戰系統。

不是：

> 已完成的 Commander-driven workflow OS。


---
[[System Overview]]