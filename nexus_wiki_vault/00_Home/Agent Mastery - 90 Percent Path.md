---
aliases: '[90% Mastery Path, New Agent Fast Track]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/ci_gate.py
status: active
tags: '[home](System Overview.md), [onboarding](Agent Onboarding - Command Pack.md), mastery,
  governance, architecture]'
title: Agent Mastery - 90 Percent Path
type: '[home](System Overview.md)'
version_scope: '[v22, v23]'
---



# Agent Mastery - 90 Percent Path

## One-sentence summary
本頁定義新 Agent 在單次 session 內達到「架構與治理 >90%、實作細節 >90%」的最小可執行學習路徑。 [Source: scripts/ops/ci_gate.py]

## Role / responsibility
- 提供固定進場順序，避免只看 Wiki 而忽略程式入口。 [Source: nexus_wiki_vault/00_Home/Agent Onboarding - Implementation Map.md]].md]
- 將治理概念直接對位到 CI/Wiki Gate 的硬規則。 [Source: scripts/ops/wiki_linter.py]
- 提供可重跑的驗證命令，確保理解不是主觀聲明。 [Source: scripts/ops/ci_gate.py]

## Upstream
- 系統全域定位來自 `[System Overview](System Overview.md)`。 [Source: nexus_wiki_vault/00_Home/System Overview.md]].md]
- 血緣與證據流來自 `[Protocol - Knowledge Lineage](../05_Protocols/Protocol - Knowledge Lineage.md)`。 [Source: nexus_wiki_vault/05_Protocols/Protocol - Knowledge Lineage.md]].md]
- 根協議錨點由 `[MUSE_PROTO](../01_System/MUSE_PROTO.md).md` 定義。 [Source: 01_System/MUSE_PROTO.md]

## Downstream
- Agent 可依本頁步驟快速完成治理與實作雙軸對位。 [Source: scripts/engine/nexus_cli.py]
- 修改 Wiki 前可先自檢 provenance 與回鏈規則。 [Source: scripts/ops/wiki_linter.py]
- 進入實作前可先完成 CI dry-run 健康檢查。 [Source: scripts/ops/ci_gate.py]

## Related modules / files
- `scripts/ops/ci_gate.py`: CI 乾跑與嚴格門禁主入口。 [Source: scripts/ops/ci_gate.py]
- `scripts/ops/wiki_linter.py`: Wiki 章節/來源/waiver 驗證器。 [Source: scripts/ops/wiki_linter.py]
- `scripts/nexus_cli.py`: CLI 相容入口（shim）。 [Source: scripts/nexus_cli.py]
- `scripts/engine/nexus_cli.py`: 主要 CLI 命令與 protocol startup gate。 [Source: scripts/engine/nexus_cli.py]
- `nexus/core/orchestrator.py`: 核心編排循環與審核流程。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_repository.py`: 狀態讀寫與最後狀態回載。 [Source: nexus/core/state_repository.py]
- `nexus/core/policy_manager.py`: episode/policy 記錄與注入治理。 [Source: nexus/core/policy_manager.py]
- `.nexus/` 與 `.nexus/contracts/sub_agent_lifecycle.json`: runtime 工件與契約痕跡。 [Source: .nexus/contracts/sub_agent_lifecycle.json]

## Source notes
- `--dry-run` 先確認 venv、contracts、benchmark script 三項存在，再進入嚴格門禁。 [Source: scripts/ops/ci_gate.py]
- strict gate 會串接 wiki audit、warning budget、benchmark replay、evidence integrity。 [Source: scripts/ops/ci_gate.py]
- Wiki 頁若非 Overview，需有 `[System Overview](System Overview.md)` 回鏈。 [Source: scripts/ops/wiki_linter.py]
- provenance 驗證可接受 repo path、vault path、以及登記中的 waiver。 [Source: scripts/ops/wiki_linter.py]

## Open questions / conflicts
- [ ] 是否要把「90% Path」做成自動化檢查腳本（輸出 mastery report）。
- [ ] 修正 4 個檔案中的剩餘失敗項目。

## 90% Mastery Checklist
1. 讀 `[System Overview](System Overview.md)` 與 `[Protocol - Knowledge Lineage](../05_Protocols/Protocol - Knowledge Lineage.md)`，建立治理視角。 [Source: nexus_wiki_vault/00_Home/System Overview.md]].md]
2. 讀 `[Agent Onboarding - Implementation Map](Agent Onboarding - Implementation Map.md)`，建立入口視角。 [Source: nexus_wiki_vault/00_Home/Agent Onboarding - Implementation Map.md]].md]
3. 執行 `uv run scripts/ops/ci_gate.py --dry-run`，確認環境健康。 [Source: scripts/ops/ci_gate.py]
4. 驗證 `[Ops - Truth Claims Register](../06_Ops/Ops - Truth Claims Register.md)` 內的所有物理聲明是否存在斷裂。 [Source: nexus_wiki_vault/06_Ops/Ops - Truth Claims Register.md]].md]
5. 讀 `scripts/engine/nexus_cli.py` 的 `nexus` group 與主要 command。 [Source: scripts/engine/nexus_cli.py]
5. 讀 `nexus/core/orchestrator.py` 的 `run_review` / `_do_loop`。 [Source: nexus/core/orchestrator.py]
6. 讀 `nexus/core/state_repository.py` 與 `nexus/core/state_contracts.py`。 [Source: nexus/core/state_repository.py]
7. 讀 `nexus/core/policy_manager.py` 與 `nexus/core/memory/ingest.py`。 [Source: nexus/core/policy_manager.py]
8. 檢查 `.nexus/contracts` 與最新 `reports` / `runs` 工件。 [Source: .nexus/contracts/sub_agent_lifecycle.json]
9. 編修 Wiki 後先跑 `uv run scripts/ops/wiki_linter.py --strict`。 [Source: scripts/ops/wiki_linter.py]
10. 進 CI 前再跑一次 `uv run scripts/ops/ci_gate.py --strict`。 [Source: scripts/ops/ci_gate.py]