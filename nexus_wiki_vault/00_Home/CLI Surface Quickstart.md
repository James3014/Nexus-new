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
