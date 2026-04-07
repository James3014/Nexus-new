---
aliases:
- Parameter Drift
- Command Evolution
confidence: high
last_compiled: 2026-04-06
owner: agent
raw_sources:
- MUSE-NEXUS Engine Specification v22
- MUSE-NEXUS Engine Specification v17.1
related_pages:
- '[[Protocol - CLI Surface|Protocol - CLI Surface]]'
- '[[System Overview|System Overview]]'
- '[[System - Unknowns and Conflicts|Unknowns]] and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags:
- protocol
- cli
- drift
- matrix
- evolution
title: Protocol - CLI Drift Matrix
type: protocol
version_scope:
- v17.1
- v22
- v23
---



# Protocol - CLI Drift Matrix

## One-sentence summary
本頁映射 Nexus CLI 命令與參數在不同主線版本間的變化，作為代碼遷移與智慧對位的導航矩陣。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **進化追蹤**: 記錄命令從單一 `nexus` 到 `nexus:plan`, `nexus:repair` 的結構性變遷。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **參數對位**: 標註 v23 智慧層引入的 `--risk`, `--auto-approve` 等新參數。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]]]
- **相容性預警**: 標註已廢棄 (Deprecated) 的舊版參數。 [Code: nexus_cli.py]

## Command & Parameter Drift Matrix

| Category | v17.1 (Hardened) | v22 (Stable) | v23 (Wisdom/v23.1) | Source Provenance |
|---|---|---|---|---|
| **Root** | `nexus <goal>` | `nexus:<phase>` | `nexus:<phase> --wise` | [Code: nexus_cli.py] |
| **Diag** | `nexus --diagnose` | `nexus:diagnose` | `nexus:diagnose --risk` | [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]]] |
| **Repair**| `nexus --repair` | `nexus:repair` | `nexus:repair --auto` | [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md] |
| **Audit** | Manual check | `nexus:audit` | `nexus:audit --guard` | [Source: ci_gate.py] |
| **Knowledge**| `[[MUSE_ENGINE_SPEC|MUSE_SPEC]].md` | `lesson_events.jsonl`| `[[Module - Memory Repository|LanceDB]] Vector` | [Source: memory_indexer.py] |

## Upstream
- **[[Protocol - CLI Surface]]**: 提供當前版本的命令全集。
- **[[Source Index]]**: 提供各版本原始規格入口。

## Downstream
- **Orchestrator Decision Layer**: 指導跨版本的命令生成邏輯。 [Code: 00_Home/System Overview.md]
- **[[System - Unknowns and Conflicts]]**: 登記參數語義漂移產生的邏輯矛盾。

## Related modules / files
- `scripts/engine/nexus_cli.py`: 實體命令實作。 [Code: nexus_cli.py]
- `MUSE-NEXUS-v17.1-HARDENED.md`: v17 系列參數基線。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Source notes
- Hardened v17.1 Spec: 定義最初的 CLI 交互約束。
- [[MUSE_ENGINE_SPEC|v23 Wisdom]] Supplement: 確立「智慧參數不破壞穩定主線」原則。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]]]

## Open questions / conflicts
- [ ] **Alias Overlap**: 部分 `nexus:*` 短別名在不同版本中的衝突。
- [ ] **Default Values**: v23 下預設 `--risk` 等級對 v22 執行流的影響。

---
[[System Overview]]
