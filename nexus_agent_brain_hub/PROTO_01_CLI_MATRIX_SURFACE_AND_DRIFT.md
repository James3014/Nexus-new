---
aliases: '[CLI Commands, Nexus CLI [[api|API]]]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags: '[protocol, cli, command, surface]'
title: Protocol - CLI Surface
type: protocol
version_scope: '[v17.1, v22, v23]'
---



# Protocol - CLI Surface

## One-sentence summary
本頁記錄 Nexus 核心命令清單與參數規範，作為外部調用與治理的權威介面映射。 [Source: nexus_wiki_vault/05_Protocols/Protocol - CLI Surface.md] [Code: nexus_cli.py]

## Role / responsibility
- **命令索引**: 映射 `plan`, `explore`, `diagnose`, `repair`, `audit`, `crystal` 等核心子命令。
- **參數約束**: 定義 `--risk`, `--auto-approve`, `--trace-id` 等關鍵參數的語義。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]] Supplement]
- **交互規範**: 規範 TTY 模式下的非同步輸入處理。 [Source: 00_Home/System Overview.md]

## Upstream
- **User Request**: 人類輸入。
- **Wisdom Layer**: 提供智慧決策偏好。

## Downstream
- **[[Flow - PXDRAC Runtime]]**: 執行命令對應的業務邏輯。
- **[[Protocol - CLI Drift Matrix]]**: 追蹤跨版本的命令進化。

## Related modules / files
- `scripts/engine/nexus_cli.py`: 進入點文件。 [Code: nexus_cli.py]
- `nexus/delivery/pilot_cli.py`: 實體 TTY 處理引擎。 [Code: pilot_cli.py]

## Source notes
- CLI Spec v17.1: 定義原始 `nexus <[[task]]>` 結構。
- Muse Engine Spec v22: 引入子命令分組機制。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Alias Conflict**: 部分舊版 alias 是否應在 v23 中正式廢棄。
- [ ] **JSON Output**: 是否所有子命令均應提供 `--json` 原始輸出流以供自動化消費。

---
[[System Overview]]
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
---
aliases: '[Nexus CLI [[quickstart|Quickstart]], CLI Minimum Set]'
confidence: high
last_compiled: '2026-04-07'
owner: agent
related_pages: ''
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags: '[[System Overview|home]], cli, [[quickstart|quickstart]]]'
title: CLI Surface [[quickstart|Quickstart]]
type: '[[System Overview|home]]'
version_scope: '[v22, v23]'
---



# CLI Surface [[QUICKSTART]]

## One-sentence summary
本頁整理 Nexus 任務最常用的 CLI 最小集合，讓 Agent 以統一命令面完成驗證、治理與交付。 [Code: scripts/engine/nexus_cli.py]

## Role / responsibility
- **最小命令集**: 提供 80% 任務會用到的核心命令。
- **知識導航**: 引導使用者探索 300+ 份跨版本 (v9, v152, v23) 的知識圖譜。
- **避免漂移**: 降低直接跑散落腳本造成的流程不一致。 [Source: scripts/ops/ci_gate.py]

## 🧠 Knowledge Exploration (知識探索)
本知識庫已透過 `nexus_linker.py` 實現了**全自動語義連結**。
- **拓全景**: 優先查看 [[Vault Topology]] 了解架構流向。
- **挖歷史**: 透過 [[01_Core/Specs/Legacy_V9/INDEX|Legacy V9]] 與 [[01_Core/Specs/Muse-Nexus-v152-upgrade/INDEX|v152 Upgrade]] 索引查看過往決策。
- **找關聯**: 在 Obsidian 中使用 `Graph View` 或 `Backlinks` 面板，查看各規格文件間的引用關係。

## Upstream
- `scripts/engine/nexus_cli.py`: 命令定義權威來源。 [Code: scripts/engine/nexus_cli.py]
- `[[Protocol - CLI Surface]]`: CLI 版本差異與語義說明。

## Downstream
- `[[Ops - Acceptance and Release]]`: 發版前命令驗證。
- `[[Ops - CI Failure Playbook]]`: 命令失敗對應修復流程。

## Related modules / files
- `scripts/engine/nexus_cli.py`
- `scripts/ops/ci_gate.py`
- `scripts/ops/nexus_task_contract_guard.py`

## Source notes
- 建議最小流程：
```bash
uv run scripts/engine/nexus_cli.py nexus:status --global
uv run scripts/engine/nexus_cli.py nexus:acceptance-check
uv run scripts/engine/nexus_cli.py nexus:contract-check --contract-file .nexus/config/task_contract.example.json --mode any --min-hits 1
uv run scripts/ops/ci_gate.py --dry-run --wiki-drift-enforce-level p0 --full-dry-run --anti-reject-enforce-level warn
```

## Open questions / conflicts
- [ ] `nexus:release-ready` 是否應明確實作為單一入口命令（目前以 gate 組合替代）。
- [ ] `nexus:acceptance-check --json` 是否應固定 schema 版本號。

---
[[System Overview]]
