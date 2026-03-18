# Nexus 文件生命週期地圖（Doc Lifecycle Map）

> [!important]
> **Status**: `ACTIVE` / `ERA-C`

更新時間：2026-03-18（Asia/Taipei）
用途：統一判定「哪份是主規格、哪份是歷史依據」，避免 agent 混用不同時期口徑。

## Era 定義
- `ERA-A`：Muse-Nexus internal/external path migration（歷史基線）
- `ERA-B`：runner/task_manifest 治理與 phase_task 接線（過渡治理）
- `ERA-C`：主重構後精準收斂 + phase health autonomy（當前主線）

## ACTIVE（當前主規格）
- `ERA-C` [INDEX.md](/Users/jameschen/Workspace/nexus/docs/INDEX.md)
- `ERA-C` [SYSTEM_ARCHITECTURE_BLUEPRINT.md](/Users/jameschen/Workspace/nexus/docs/SYSTEM_ARCHITECTURE_BLUEPRINT.md)
- `ERA-C` [2026-03-18_Nexus_Phase_Health_Implementation_Plan.md](/Users/jameschen/Workspace/nexus/docs/2026-03-18_Nexus_Phase_Health_Implementation_Plan.md)
- `ERA-C` [2026-03-18_Nexus_Phase_Health_Autonomy_Design.md](/Users/jameschen/Workspace/nexus/docs/2026-03-18_Nexus_Phase_Health_Autonomy_Design.md)
- `ERA-C` [EXEC_LIVE_STATUS.md](/Users/jameschen/Workspace/nexus/docs/EXEC_LIVE_STATUS.md)

## REFERENCE（可參考，不可覆蓋 ACTIVE）
- `ERA-B` [19_AGENT_TASK_PACK_v1.md](/Users/jameschen/Workspace/nexus/docs/19_AGENT_TASK_PACK_v1.md)
- `ERA-B` [12_AGENT_EXECUTION_GUIDE.md](/Users/jameschen/Workspace/nexus/docs/12_AGENT_EXECUTION_GUIDE.md)
- `ERA-B` [17_GEMINI_CODEX_HANDOFF_USAGE.md](/Users/jameschen/Workspace/nexus/docs/17_GEMINI_CODEX_HANDOFF_USAGE.md)
- `ERA-B` [18_REFACTOR_PROGRESS_BOARD.md](/Users/jameschen/Workspace/nexus/docs/18_REFACTOR_PROGRESS_BOARD.md)
- `ERA-B` [2026-03-18_Nexus_第二輪精準收斂重構計畫.md](/Users/jameschen/Workspace/nexus/docs/2026-03-18_Nexus_第二輪精準收斂重構計畫.md)
- `ERA-A` [08_MIGRATION_RUNBOOK_V1_5_2_PLUS.md](/Users/jameschen/Workspace/nexus/docs/08_MIGRATION_RUNBOOK_V1_5_2_PLUS.md)
- `ERA-A` [09_STATE_CONTRACT_DRAFT.md](/Users/jameschen/Workspace/nexus/docs/09_STATE_CONTRACT_DRAFT.md)
- `ERA-A` [10_IMPLEMENTATION_SEQUENCE.md](/Users/jameschen/Workspace/nexus/docs/10_IMPLEMENTATION_SEQUENCE.md)
- `ERA-A` [15_MIGRATION_SAFETY_VALIDATOR_PLAN.md](/Users/jameschen/Workspace/nexus/docs/15_MIGRATION_SAFETY_VALIDATOR_PLAN.md)

## ARCHIVE（封存，禁止作為執行依據）
- `ERA-A` [01_CURRENT_STATE.md](/Users/jameschen/Workspace/nexus/docs/01_CURRENT_STATE.md)
- `ERA-A` [02_TARGET_ARCHITECTURE.md](/Users/jameschen/Workspace/nexus/docs/02_TARGET_ARCHITECTURE.md)
- `ERA-A` [03_GAP_ANALYSIS.md](/Users/jameschen/Workspace/nexus/docs/03_GAP_ANALYSIS.md)
- `ERA-A` [04_REFACTOR_ROADMAP.md](/Users/jameschen/Workspace/nexus/docs/04_REFACTOR_ROADMAP.md)
- `ERA-A` [11_FIRST_CUT_FILE_PLAN.md](/Users/jameschen/Workspace/nexus/docs/11_FIRST_CUT_FILE_PLAN.md)

## 執行規則（強制）
1. 任務新增、驗收口徑、gate 門檻，只能引用 `ACTIVE`。
2. 若 agent 回報引用 `REFERENCE`，必須補一段「與 ACTIVE 對齊」說明。
3. `ARCHIVE` 僅可用於追溯，不能作為當輪實作與驗收依據。
4. 每次 `INDEX.md` 變更時，需同步檢查本文件分級是否仍正確。
