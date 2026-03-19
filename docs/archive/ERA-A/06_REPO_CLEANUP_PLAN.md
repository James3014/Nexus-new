# Muse-Nexus Repo Cleanup Plan

## Goal

這份文件的目的不是立刻大掃除，而是先把 repo 內哪些東西屬於：

- 現役主幹
- 可抽象為核心模組
- 歷史殘留 / 遷移副本
- 執行產物 / 應忽略檔

說清楚，讓後續整理不會誤刪有效腳本，也不會讓未來架構演進持續被舊殼污染。

## Current Directory Shape

```text
scripts/
├── root-level operational scripts
├── core/
├── _migrated_from_obsidian/
├── Templates/
├── tools/
└── __pycache__/
```

## Cleanup Principles

1. 先標記，再搬動，不直接刪除。
2. 先決定主幹入口，再處理 duplicate。
3. 先清理 generated artifacts，再清理 historical copies。
4. 每次只做一類清理，避免把重構、搬檔、功能修改混成一次提交。

## Category Assessment

### A. Root-Level `scripts/`

Status:

- 視為目前的現役主幹區。

Observed characteristics:

- 大量 operational scripts 直接放在 root level
- 部分檔案已被其他模組引用
- 多數路徑與既有工作流直接耦合

Recommendation:

- 在正式重構前，暫時把 root-level `scripts/` 視為 canonical source
- 不要先把大量 root scripts 搬進新目錄
- 先為每個核心腳本標記角色與責任

Likely keepers:

- `codex_loop_brain.py`
- `workspace_manager.py`
- `git_manager.py`
- `drclaw_diagnosis.py`
- `brain_search_v2.py`
- `brain_search_v3.py`
- `brain_search_v4.py`
- `flash_ingest_v2.py`
- `pre_write_quality_gate.py`
- `app.py`
- `script_dashboard.py`

### B. `scripts/core/`

Status:

- 高機率是「模組化重構嘗試」的殘留與部分現役混合區。

Observed characteristics:

- 包含 `git_manager.py`、`workspace_manager.py`、`drclaw_diagnosis.py` 等 root-level 對應版本
- `codex_loop_brain.py` 已直接 import `core.*`
- 說明這個目錄不是純歷史副本，而是正在被部分主幹使用

Risk:

- root-level 與 `core/` 兩套實作並存，容易產生：
  - import 邊界不清
  - 修一份漏一份
  - 實作漂移

Recommendation:

- 把 `scripts/core/` 視為「未完成的 library layer」
- 先盤點哪些 root scripts 真的依賴 `core/`
- 之後採用單向規則：
  - root-level orchestration script 可以 import `core/`
  - `core/` 不反向依賴 root-level scripts

Action:

- 為 `core/` 內檔案建立 ownership 清單
- 標記：
  - canonical
  - duplicate
  - deprecated candidate

### C. `scripts/_migrated_from_obsidian/`

Status:

- 高機率屬於歷史遷移副本，不應繼續當正式主幹。

Observed characteristics:

- 幾乎是整批舊 scripts 快照
- 檔名與 root-level `scripts/` 高度重複
- 目前未看到明確 runtime 入口直接依賴此路徑

Recommendation:

- 視為 archive candidate
- 不應再接受功能開發
- 不應再作為新的 import source

Suggested handling:

1. 先加一份目錄說明，標記為 historical snapshot。
2. 搜尋是否仍有任何程式直接引用此目錄。
3. 若無 runtime 依賴：
   - 移到 `archive/obsidian-migration/`
   - 或保留原地但標記 read-only / deprecated

### D. `scripts/__pycache__/` and `scripts/core/__pycache__/`

Status:

- 純 generated artifacts

Observed characteristics:

- 目前仍被 git 追蹤，導致 repo 持續髒掉

Recommendation:

- 應從版本控制中移除
- 保留 `.gitignore` 規則，防止再次進入 index

Important note:

- 因為這些檔案目前已被 git 追蹤，僅新增 `.gitignore` 不足以清除
- 需要後續專門做一次 index cleanup

Suggested future command scope:

```text
git rm --cached <tracked pycache files>
```

這一步應單獨成一個 cleanup commit，不與功能修改混在一起。

### E. `.venv/`, `.trees/`, `.ruff_cache/`, `.env`

Status:

- 本機工作產物 / 本機環境資料

Recommendation:

- 不應進入版本控制
- 已由 `.gitignore` 覆蓋

## Proposed Canonical Layout

這不是立即搬遷方案，而是目標整理方向：

```text
Muse-Nexus/
├── docs/
├── scripts/
│   ├── commander/
│   ├── engines/
│   ├── memory/
│   ├── audit/
│   ├── ops/
│   ├── templates/
│   └── tools/
├── archive/
│   └── obsidian-migration/
└── .muse_state/   # future runtime state, not committed
```

對應原則：

- orchestration 類：放 `commander/`
- phase engines：放 `engines/`
- brain / ingest / retrieval：放 `memory/`
- audit / quality / hygiene：放 `audit/`
- worktree / git / utility scripts：放 `ops/`
- 舊遷移快照：放 `archive/`

## Recommended Cleanup Sequence

### Step 1. Generated Artifacts Cleanup

Scope:

- `scripts/__pycache__/`
- `scripts/core/__pycache__/`
- 任何已追蹤的 `*.pyc`

Outcome:

- repo status 不再被執行產物持續污染

### Step 2. Historical Snapshot Freeze

Scope:

- `scripts/_migrated_from_obsidian/`

Outcome:

- 明確標記為 historical / archive candidate
- 禁止新增功能到此目錄

### Step 3. Core Ownership Mapping

Scope:

- root-level `scripts/*.py`
- `scripts/core/*.py`

Outcome:

- 每個重複檔案都標明：
  - 誰是 canonical
  - 誰是 wrapper
  - 誰是 deprecated

### Step 4. Directory Restructuring

Scope:

- 只在 ownership 清楚後才搬動

Outcome:

- 將 repo 從「平鋪腳本倉」收斂成「可導航的系統目錄」

## Immediate Backlog

- [ ] 建立 root scripts vs `scripts/core/` 的對照表
- [ ] 確認 `_migrated_from_obsidian/` 是否仍被任何檔案引用
- [ ] 確認哪些 `__pycache__` 已被 git 追蹤
- [ ] 規劃一次獨立的 `pycache cleanup` 提交
- [ ] 為 historical snapshot 加上 deprecated 標記
- [ ] 為核心現役腳本建立 responsibility map

## Practical Conclusion

Muse-Nexus 現在最需要的 repo 清理，不是大量搬檔，而是先解決三件事：

1. 把 generated artifacts 從版本控制移除。
2. 把 `_migrated_from_obsidian/` 從現役工作流中降級為歷史副本。
3. 把 root-level `scripts/` 與 `scripts/core/` 的 ownership 關係定義清楚。

只有這三件事先穩住，後面的 Commander / Context Hub / state contracts 重構才不會繼續被目錄混亂拖累。
