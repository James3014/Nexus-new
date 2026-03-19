# Muse-Nexus Agent Execution Guide

## Purpose

這份文件定義未來把 Muse-Nexus implementation task 交給 agent 時，agent 應怎麼讀文件、怎麼選範圍、怎麼施工。

這不是架構文件，而是施工操作手冊。

## Agent Mission

Agent 的任務不是「自由發揮重構」，而是：

> 在既有文件約束下，按順序落地最小可驗證的 Muse-Nexus 新架構能力。

## Required Read Order

開始改 code 前，agent 必讀順序：

1. `docs/00_PROJECT_INDEX.md`
2. `docs/01_CURRENT_STATE.md`
3. `docs/02_TARGET_ARCHITECTURE.md`
4. `docs/04_REFACTOR_ROADMAP.md`
5. `docs/08_MIGRATION_RUNBOOK_V1_5_2_PLUS.md`
6. `docs/09_STATE_CONTRACT_DRAFT.md`
7. `docs/10_IMPLEMENTATION_SEQUENCE.md`
8. `docs/11_FIRST_CUT_FILE_PLAN.md`

若要處理 repo 結構與 ownership，再加讀：

9. `docs/06_REPO_CLEANUP_PLAN.md`
10. `docs/07_SCRIPT_OWNERSHIP_MAP.md`

若要跑現版 Gemini + Codex 施工流程，再加讀：

11. `docs/17_GEMINI_CODEX_HANDOFF_USAGE.md`
12. `docs/18_REFACTOR_PROGRESS_BOARD.md`

## Non-Negotiable Rules

1. JSON is the source of truth
   - 不得把 TOON 寫進 `.muse_state`
   - TOON 只允許出現在 Context Hub 的 prompt serialization

2. Contract first
   - 先建 contract / read-write helpers，再改 phase 行為

3. Internal first
   - 第一波不接真 external routing
   - 只設 `external_needed` / `needs_research`

4. Minimal diff
   - 第一波先新增模組
   - 對 `codex_loop_brain.py` / `drclaw_diagnosis.py` 只做最小必要修改

5. Do not refactor unrelated systems
   - 不整理 dashboard
   - 不搬大量目錄
   - 不清 historical snapshot
   - 不碰 memory engine 核心

6. Freeze baseline before risky edits
   - 進入 repair core 或 contract migration 前，先記錄 baseline state
   - 若有 half-upgrade risk，先模擬 legacy / partial state

7. Human owns logic review
   - agent 建骨架與 prototype
   - human 審 schema naming、router logic、gatekeeper semantics

## Allowed First-Cut Scope

Agent 第一波只允許處理：

- `scripts/core/state_contracts.py`
- `scripts/core/state_io.py`
- `scripts/core/context_hub.py`
- `scripts/core/reflection_store.py`
- `scripts/core/skills_router.py`
- `scripts/codex_loop_brain.py`
- `scripts/drclaw_diagnosis.py`

## Preferred Workflow

### Step 1. Re-state scope

Agent 先在回應中明確說出：

- 這次只做哪一段
- 不做哪一段
- 會碰哪些檔案

### Step 2. Inspect current code

Agent 必須先讀：

- 現有入口檔
- 現有 import 關係
- 現有資料結構

不得直接憑文件假設 code 已存在某模組。

### Step 3. Implement smallest coherent slice

優先順序：

1. contracts / state io
2. context hub skeleton
3. skills router skeleton
4. repair integration
5. diag integration

### Step 4. Verify

至少要驗證：

- import 沒壞
- JSON read/write path 正常
- legacy 欄位缺失時不爆
- touched files 有基本 smoke pass
- 若涉及 contract / repair loop，需做 half-upgraded state 驗證
- 若有 router logic，需輸出 decision reason / score breakdown
- 若有 validator，需說明 gatekeeper mode 是否已跑
- 若有 baseline，需回報 token / 延遲變化

### Step 5. Report

Agent 回報時必須包含：

- touched files
- what changed
- what was not implemented
- verification performed
- residual risks
- baseline freeze / compatibility assumptions

## Anti-Patterns

以下行為視為違規施工：

- 一次改完整 Commander / Context Hub / Router / Viz / External
- 直接重寫 `codex_loop_brain.py`
- 把 TOON 當成 state format
- 為了讓新設計漂亮而大量搬目錄
- 沒有契約就先寫 phase 行為
- 沒做 baseline freeze 就重寫 repair core
- 沒有 decision reason 就讓 skills router 自動選 skill
- 沒做 repo hygiene 檢查就引入新的 local artifact / cache noise

## Suggested Task Prompt Template

可以直接把下面這段交給 agent：

```text
Read these files first in order:
docs/00_PROJECT_INDEX.md
docs/01_CURRENT_STATE.md
docs/02_TARGET_ARCHITECTURE.md
docs/04_REFACTOR_ROADMAP.md
docs/08_MIGRATION_RUNBOOK_V1_5_2_PLUS.md
docs/09_STATE_CONTRACT_DRAFT.md
docs/10_IMPLEMENTATION_SEQUENCE.md
docs/11_FIRST_CUT_FILE_PLAN.md

Task:
Implement only the first-cut internal path for Muse-Nexus.

Scope allowed:
- scripts/core/state_contracts.py
- scripts/core/state_io.py
- scripts/core/context_hub.py
- scripts/core/reflection_store.py
- scripts/core/skills_router.py
- scripts/codex_loop_brain.py
- scripts/drclaw_diagnosis.py

Rules:
- JSON remains the only authority state format.
- Do not implement real external/Felo routing.
- Do not refactor unrelated modules.
- Prefer additive changes and compatibility-safe reads.
- Before editing, restate which files you will touch and why.
- After editing, report changed files, tests/smoke checks, and residual risks.
```

## Human Review Checklist For Agent Output

人工 reviewer 應特別看：

- 新欄位名稱是否與文件一致
- `.muse_state` 檔名是否一致
- 是否把 external path 提前寫死
- 是否把 TOON 滲透到 state 層
- 是否超出 first-cut scope

## Practical Conclusion

把 implementation 交給 agent 時，最重要的不是 prompt 越長越好，而是：

> 文件讀取順序、允許碰的檔案、禁止碰的範圍、以及回報格式要先鎖死。

## Current Runtime Handoff (Gemini + Codex)

現版可執行工作流：

```text
Gemini edits
  -> codex-loop review
    -> /tmp/codex_next_action.json
      -> gemini_handoff prompt
        -> Gemini next round
```

常用命令：

```bash
scripts/codex-loop.sh --mode audit <files...> --emit-gemini-handoff
scripts/codex-loop.sh --handoff-only --emit-gemini-handoff --handoff-output /tmp/gemini_task.txt
```
