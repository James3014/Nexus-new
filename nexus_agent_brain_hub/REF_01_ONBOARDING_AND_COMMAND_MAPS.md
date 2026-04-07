---
aliases: '[Onboarding, Command Runbook, Essential Commands, Command Pack]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags: '[[System Overview|home]], onboarding, commands, runbook]'
title: Agent Onboarding - Command Pack
type: '[[System Overview|home]]'
version_scope: '[v17.1, v22, v23]'
---



# Agent Onboarding - Command Pack

## One-sentence summary
本頁提供 Nexus Agent 新手進場的核心指令包，涵蓋環境檢查、Wiki 治理與發版校驗。 [Source: scripts/engine/nexus_cli.py]

## Role / responsibility
- **標準執行流**: 確保新 Agent 能以一致的命令路徑完成系統初始化與修改驗證。 [Source: scripts/engine/nexus_cli.py]
- **防錯引導**: 提供 `dry-run` 優先的執行習慣。

## 🧠 Phase 0: Context Injection (脈絡注入)
在執行任何指令前，Agent **必須**先建立系統心理模型。若無視背景脈絡直接執行指令，將被視為高風險行為。
- **架構掃描**: 閱讀 [[System Overview]] 了解 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] 治理邏輯。
- **地景確認**: 查閱 [[Vault Topology]] 確認當前工作區在知識圖譜中的位置。
- **歷史溯源**: 若涉及核心協議修改，必須先查閱 [[01_Core/Specs/Legacy_V9/INDEX|Legacy V9 Index]] 確保不違反既有架構決策。

## 🛡️ Phase 1: 環境與健康檢查 (Health Check)
```bash
uv run scripts/ops/ci_gate.py --dry-run [Source: scripts/ops/ci_gate.py]
```

## Upstream
- **Nexus CLI**: `scripts/engine/nexus_cli.py` 定義核心入口。 [Source: scripts/engine/nexus_cli.py]

## Downstream
- **[[Ops - CI Failure Playbook]]**: 若命令失敗，請前往此頁搜尋修復。

## Related modules / files
- `scripts/ops/wiki_linter.py`: 治理檢查。 [Source: scripts/ops/wiki_linter.py]

## Source notes
- v22 Engine Spec: 要求所有指令必須具備物理來源。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Interactive**: 是否提供互動式選單。---
aliases: '[Implementation Map, Nexus Map, Entry Point Map]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/ci_gate.py
status: active
tags: '[[System Overview|home]], [[Agent Onboarding - Command Pack|onboarding]], implementation,
  governance]'
title: Agent [[Agent Onboarding - Command Pack|Onboarding]] - Implementation Map
type: '[[System Overview|home]]'
version_scope: '[v22, v23]'
---



# Agent [[Agent Onboarding - Command Pack|Onboarding]] - Implementation Map

## One-sentence summary
本頁將 Nexus 的宏觀架構與微觀實體檔案進行物理對照，作為 Agent 進場後的導航地圖。 [Source: scripts/ops/ci_gate.py]

## Role / responsibility
- **消除實作迷霧**: 明確標註每個治理概念在 Repo 中的具體入口。 [Source: 00_Home/System Overview.md]] - Implementation Map.md]
- **導航加速**: 提供從 [[System Overview]] 到 `/nexus/core` 的最短路徑。

## Implementation Map (實作地圖)

### 1. 治理與門禁 (Governance & Gate)
- **[[CD Promotion Gate|CI Gate]] 硬閘**: `scripts/ops/ci_gate.py` [Code: scripts/ops/ci_gate.py]
- **Wiki Linter**: `scripts/ops/wiki_linter.py` [Code: scripts/ops/wiki_linter.py]
- **故障排除**: 參考 `[[Ops - CI Failure Playbook]]`。 [Source: nexus_wiki_vault/06_Ops/Ops - CI Failure Playbook.md]].md]

## Upstream
- **[[System Overview]]**: 宏觀定位。 [Source: nexus_wiki_vault/00_Home/System Overview.md]].md]

## Downstream
- **[[Module - Implementation Responsibility Matrix]]**: 詳細責任矩陣。

## Related modules / files
- `scripts/ops/ci_gate.py`: 門禁核心。 [Source: scripts/ops/ci_gate.py]

## Source notes
- v22 Engine Spec: 要求「凡實作必有地圖」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Dynamic Updates**: 是否由 Linter 自動更新地圖次數。---
aliases: '[90% Mastery Path, New Agent Fast Track]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/ci_gate.py
status: active
tags: '[[System Overview|home]], [[Agent Onboarding - Command Pack|onboarding]], mastery,
  governance, architecture]'
title: Agent Mastery - 90 Percent Path
type: '[[System Overview|home]]'
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
- 系統全域定位來自 `[[System Overview]]`。 [Source: nexus_wiki_vault/00_Home/System Overview.md]].md]
- 血緣與證據流來自 `[[Protocol - Knowledge Lineage]]`。 [Source: nexus_wiki_vault/05_Protocols/Protocol - Knowledge Lineage.md]].md]
- 根協議錨點由 `[[MUSE_PROTO]].md` 定義。 [Source: 01_System/MUSE_PROTO.md]

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
- Wiki 頁若非 Overview，需有 `[[System Overview]]` 回鏈。 [Source: scripts/ops/wiki_linter.py]
- provenance 驗證可接受 repo path、vault path、以及登記中的 waiver。 [Source: scripts/ops/wiki_linter.py]

## Open questions / conflicts
- [ ] 是否要把「90% Path」做成自動化檢查腳本（輸出 mastery report）。
- [ ] 修正 4 個檔案中的剩餘失敗項目。

## 90% Mastery Checklist
1. 讀 `[[System Overview]]` 與 `[[Protocol - Knowledge Lineage]]`，建立治理視角。 [Source: nexus_wiki_vault/00_Home/System Overview.md]].md]
2. 讀 `[[Agent Onboarding - Implementation Map]]`，建立入口視角。 [Source: nexus_wiki_vault/00_Home/Agent Onboarding - Implementation Map.md]].md]
3. 執行 `uv run scripts/ops/ci_gate.py --dry-run`，確認環境健康。 [Source: scripts/ops/ci_gate.py]
4. 驗證 `[[Ops - Truth Claims Register]]` 內的所有物理聲明是否存在斷裂。 [Source: nexus_wiki_vault/06_Ops/Ops - Truth Claims Register.md]].md]
5. 讀 `scripts/engine/nexus_cli.py` 的 `nexus` group 與主要 command。 [Source: scripts/engine/nexus_cli.py]
5. 讀 `nexus/core/orchestrator.py` 的 `run_review` / `_do_loop`。 [Source: nexus/core/orchestrator.py]
6. 讀 `nexus/core/state_repository.py` 與 `nexus/core/state_contracts.py`。 [Source: nexus/core/state_repository.py]
7. 讀 `nexus/core/policy_manager.py` 與 `nexus/core/memory/ingest.py`。 [Source: nexus/core/policy_manager.py]
8. 檢查 `.nexus/contracts` 與最新 `reports` / `runs` 工件。 [Source: .nexus/contracts/sub_agent_lifecycle.json]
9. 編修 Wiki 後先跑 `uv run scripts/ops/wiki_linter.py --strict`。 [Source: scripts/ops/wiki_linter.py]
10. 進 CI 前再跑一次 `uv run scripts/ops/ci_gate.py --strict`。 [Source: scripts/ops/ci_gate.py]---
aliases: '[Boot Sequence, First 30 Minutes, Agent Boot SOP]'
confidence: high
last_compiled: '2026-04-07'
owner: agent
related_pages: ''
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags: '[[System Overview|home]], [[Agent Onboarding - Command Pack|onboarding]], boot,
  sop]'
title: Agent Boot Sequence
type: '[[System Overview|home]]'
version_scope: '[v22, v23]'
---



# Agent Boot Sequence

## One-sentence summary
本頁定義新 Agent 進場後前 30 分鐘的最小可執行流程，確保所有任務先通過 Nexus 基線門禁再開始實作。 [Source: scripts/engine/nexus_cli.py]

## Role / responsibility
- **啟動標準化**: 提供新 Agent 的固定啟動順序，降低環境誤判與流程漂移。
- **失敗早檢出**: 先做命令面與治理 gate 檢查，避免後段返工。 [Source: scripts/ops/ci_gate.py]

## Upstream
- `[[MUSE_PROTO]].md`: 定義全域協議錨點。 [Source: 01_System/MUSE_PROTO.md]
- `scripts/engine/nexus_cli.py`: 定義 Nexus 命令面。 [Code: scripts/engine/nexus_cli.py]

## Downstream
- `[[Agent Onboarding - Implementation Map]]`: 進入任務執行路徑。
- `[[Ops - CI Failure Playbook]]`: 若 preflight 失敗時的修復入口。

## Related modules / files
- `scripts/engine/nexus_cli.py`
- `scripts/ops/ci_gate.py`
- `scripts/ops/wiki_linter.py`

## 🗺️ Step 0: Landscape Discovery (地景探索)
新 Agent 進場的第一動作**不是**跑指令，而是確立座標。
1.  **確認地圖**: 查閱 [[Vault Topology]] 建立架構全景。
2.  **建立脈絡**: 閱讀 [[System Overview]] 了解當前治理基線。
3.  **安全考古**: 若任務涉及深層邏輯，必須查閱 [[01_Core/Specs/Legacy_V9/INDEX|Legacy Index]]。

## Source notes
- 建議固定步驟：
```bash
uv run scripts/engine/nexus_cli.py --help
uv run scripts/ops/ci_gate.py --dry-run
uv run scripts/ops/wiki_linter.py --strict
```

## Open questions / conflicts
- [ ] 是否要把 `acceptance-check` 納入所有任務啟動前必跑清單。
- [ ] 是否要強制回報 `nexus_participation_ratio` 作為啟動合規證據。