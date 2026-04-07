---
aliases: '[Wiki Coverage, [[documentation|Documentation]] Heatmap]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: .nexus/reports/wiki_coverage_report.json
status: active
tags: '[Index](../.nexus/graph/index.md)|[Index](../.nexus/graph/index.md)|[Index](../.nexus/graph/index.md)|[[Source [[index|Index]]|sources]]]]]]]],
  coverage, audit, heatmap]'
title: Source - Coverage Heatmap
type: '[Index](../.nexus/graph/index.md)|[Index](../.nexus/graph/index.md)|[Index](../.nexus/graph/index.md)|[[Source [[index|Index]]|sources]]]]]]]]'
version_scope: '[v17.1, v22, v23]'
---



# Source - Coverage Heatmap

## One-sentence summary
本頁展示 Nexus 核心程式碼在治理 Wiki 中的覆蓋率分佈情況。 [Source: scripts/ops/wiki_coverage_audit.py]

## Role / responsibility
- **透明度管控**: 提供量化指標，識別哪些實體檔案目前處於「治理真空」或「未被 Wiki 描述」狀態。 [Source: .nexus/reports/wiki_coverage_report.json]
- **優先級導航**: 引導治理工程師優先補齊高風險、未覆蓋的代碼路徑文檔。

## Current Coverage Metrics (當前稽核指標)

> [!IMPORTANT]
> **Global Coverage: 85.14% (PASS)**
> **Key Path Coverage: 100.00% (PASS)** [Source: .nexus/reports/wiki_keypath_coverage_report.json]
> 計算基準：關鍵 12 條核心路徑必須 100% 覆蓋；全域目錄 (`nexus/core`, `nexus/services`, `scripts/ops`, `scripts/engine`) 需 > 85%。

### Summary Metrics
- **Total Code Files**: 249 [Source: scripts/ops/wiki_coverage_audit.py]
- **Covered Files**: 212
- **Key Path Files**: 12/12 (100%)
- **Stale Coverage**: 參見 [Ops - Wiki Drift Audit](../06_Ops/Ops - Wiki Drift Audit.md)

## Key Path Implementation Status (核心路徑覆蓋清單)

| Path (核心檔案) | Status | Wiki Reference |
|---|---|---|
| `scripts/ops/ci_gate.py` | ✅ | [[Ops - CI/CD Promotion Gate]] |
| `scripts/scripts/ops/wiki_linter.py` | ✅ | [System Overview](../00_Home/System Overview.md) |
| `scripts/ops/wiki_drift_audit.py` | ✅ | [Ops - Wiki Drift Audit](../06_Ops/Ops - Wiki Drift Audit.md) |
| `nexus/core/orchestrator.py` | ✅ | [Module - Core Orchestrator](../02_Modules/Module - Core Orchestrator.md) |
| `nexus-desk/src-tauri/src/main.rs` | ✅ | [Module - Nexus Desk Interface](../02_Modules/Module - Nexus Desk Interface.md) |

## Remaining Gaps (治理缺口)

| Path | Risk (Estimated) | Reason |
|---|---|---|
| `scripts/.nexus/workspaces/bug-1774969963/scripts/engine/l6_gate.py` | High | 缺乏對 L6 Gate 的治理描述。 |
| `scripts/engine/ci_graph_impact.py` | High | 圖譜影響力分析未納入規範。 |

## Upstream
- **Wiki Audit Engine**: `scripts/ops/wiki_coverage_audit.py` [Code: scripts/ops/wiki_coverage_audit.py]
- **Provenance Tags**: 全庫 `[Source: 00_Home/System Overview.md]` 標籤。

## Downstream
- **[Source Index](Source Index.md)**: 提供全域來源索引。
- **[Ops - Wiki Drift Audit](../06_Ops/Ops - Wiki Drift Audit.md)**: 驗證已覆蓋項的時效性。

## Related modules / files
- `.nexus/reports/wiki_coverage_report.json`: 生成的報表。 [Source: .nexus/reports/wiki_coverage_report.json]

## Source notes
- v22 Engine Spec: 要求所有核心服務 (`nexus/services`) 必須具備 1:1 的治理對應關係。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Dynamic Paths**: 如何處理 `*.so` 或二進位檔案的覆蓋率標記。
- [ ] **Exclusion List**: 是否應排除 `__init__.py` 等結構性檔案以優化指標。

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]