# H7-8X Clean Worktree H8 Entry Plan v0

**日期**: 2026-06-26  
**狀態**: `H7_8X_CLEAN_WORKTREE_H8_ENTRY_PLAN_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `PLAN_ONLY=true`, `REPORT_ONLY=true`, `READ_ONLY=true`, `CURRENT_WORKSPACE_PRESERVED=true`, `NO_FILES_DELETED`, `NO_FILES_MOVED`, `NO_FILES_ARCHIVED`, `NO_FILES_RESTORED`, `NO_GIT_CLEAN`, `NO_GIT_RESTORE`, `NO_GIT_RM`, `NO_WORKTREE_CREATED`, `NO_LOCAL_MODEL_RUN`, `NO_BENCHMARK_RUNTIME_RUN`, `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_MODEL_EXECUTION`, `NO_H8_RUNTIME`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 plan-only / report-only 產出。本任務期間未建立 worktree、未清理檔案、未刪除任何檔案、未執行任何 runtime 命令。所有命令均為未來候選，等待 owner 批准。

---

## 0. Status / Safety Boundary

* **status**: `H7_8X_CLEAN_WORKTREE_H8_ENTRY_PLAN_DRAFT_READY_FOR_REVIEW`
* **plan_only=true** (僅計畫)
* **report_only=true** (僅報告)
* **read_only=true** (僅讀取)
* **current_workspace_preserved=true** (當前工作區已保留)
* **no files deleted** (未刪除檔案)
* **no files moved** (未移動檔案)
* **no files archived** (未封存檔案)
* **no files restored** (未還原檔案)
* **no git clean** (未執行 git clean)
* **no git restore** (未執行 git restore)
* **no git rm** (未執行 git rm)
* **no worktree created** (未建立 worktree)
* **no local model run** (未執行 local model)
* **no benchmark runtime run** (未執行 benchmark runtime)
* **no runtime behavior change** (無執行期行為變更)
* **no provider call** (無 provider 呼叫)
* **no model call** (無模型調用)
* **no network call** (無網路存取)
* **no model load** (無模型載入)
* **no model execution** (無模型執行)
* **no H8 runtime** (H8 執行期未啟動)
* **no production code modified** (未修改生產代碼)
* **no tests modified** (未修改測試)
* **no CI modified** (未修改 CI)
* **workspace_cleaned=false** (工作區未清理)
* **data_loss_risk_executed=false** (無資料遺失風險)
* **production_ready=false** (生產就緒為 false)
* **public_claim_allowed=false** (公開宣稱許可為 false)

---

## 1. Scope

* **H7-8X avoids cleanup-first**: 不採用先清理再進入 H8 的方式。
* **H7-8X preserves current dirty workspace**: 保留當前所有 dirty files 不動。
* **H7-8X plans a clean worktree entry into H8**: 規劃從 clean worktree 進入 H8。
* **H7-8X does not execute worktree creation**: 不建立 worktree。
* **H7-8X does not make H8 runtime ready**: 不使 H8 runtime 就緒。

---

## 2. Why Not Clean Now

| Command | Risk | Why deferred |
| :--- | :--- | :--- |
| `git restore` | can discard tracked modifications | current artifacts may be useful for later forensic review |
| `git clean` | can delete untracked files | untracked artifacts may contain meaningful evidence |
| `git rm --cached` | changes repository tracking policy | should be a deliberate separate decision |
| All of the above | data loss risk | owner explicitly chose to preserve workspace |

**Therefore cleanup is deferred.** H7-8 cleanup approval plan remains useful documentation, but execution is deferred until owner explicitly approves.

---

## 3. Clean Worktree Strategy

| Element | Value |
| :--- | :--- |
| **Base commit** | `72c2c601` — `docs: add H7-8 workspace cleanup approval plan` |
| **Future worktree path** | `../nexus-h8-clean` |
| **Current checkout** | remains untouched (all dirty files preserved) |
| **H8 entry point** | from committed H7 safe gates in clean worktree |
| **Dirty artifacts** | remain preserved in original checkout for later review |

---

## 4. H8 Entry Gate

### H7 Focused Gate Command

```bash
python3 -m pytest \
  tests/benchmark/test_h7_capability_receipt_denial_fields.py \
  tests/benchmark/test_h7_public_claim_evidence_linkage.py \
  tests/benchmark/test_h7_route_receipt_schema_consistency.py \
  tests/benchmark/test_h7_route_truth_protection.py \
  tests/benchmark/test_h7_recovery_readiness_blockers.py \
  -q
```

**Expected result**: 153 passed

**Requirement**: clean worktree `git status --short` must be empty before H8 starts.

---

## 5. What Still Is Not Ready

| Item | Status |
| :--- | :--- |
| H8 runtime | not started |
| local model adapter | not enabled |
| provider/model execution | deny-by-default |
| recovery/resume runtime | not ready |
| Reconstructable Runtime | not ready |
| ACRouter | not enabled |
| production_ready | false |
| public_claim_allowed | false |

---

## 6. Recommended Next Task

### H8-0 Controlled Local Model Adapter Reality Map

This next task must remain **report-only / test-plan-only** unless explicitly approved.

---

## 7. Acceptance Criteria

* [x] Report exists: `docs/reports/h7_8x_clean_worktree_h8_entry_plan_v0.md`
* [x] No production code modified
* [x] No tests modified
* [x] No CI modified
* [x] No files deleted/moved/restored
* [x] No git clean run
* [x] No git restore run
* [x] No git rm run
* [x] No worktree created
* [x] Current workspace preserved
* [x] Future worktree command documented
* [x] H7 focused gate command documented (153 passed verified)
* [x] Data loss risk avoided
* [x] Final state: `H7_8X_CLEAN_WORKTREE_H8_ENTRY_PLAN_DRAFT_READY_FOR_REVIEW`

---

## 8. Final State

`H7_8X_CLEAN_WORKTREE_H8_ENTRY_PLAN_DRAFT_READY_FOR_REVIEW`

### Forbidden Final States

* `WORKSPACE_CLEANED`
* `FILES_DELETED`
* `GIT_CLEAN_EXECUTED`
* `GIT_RESTORE_EXECUTED`
* `GIT_RM_EXECUTED`
* `WORKTREE_CREATED`
* `H8_RUNTIME_STARTED`
* `LOCAL_MODEL_ENABLED`
* `PRODUCTION_READY`
* `PUBLIC_CLAIM_ALLOWED`

---

## 9. Verification Commands

```bash
# Report exists
test -f docs/reports/h7_8x_clean_worktree_h8_entry_plan_v0.md && echo H7_8X_REPORT_EXISTS

# Safety boundary strings
grep -nE "H7_8X_CLEAN_WORKTREE_H8_ENTRY_PLAN_DRAFT_READY_FOR_REVIEW|plan_only=true|current_workspace_preserved=true|no files deleted|no files restored|no git clean|no git restore|no git rm|no worktree created|no local model run|no provider call|no model call|no network call|workspace_cleaned=false|data_loss_risk_executed=false|production_ready=false|public_claim_allowed=false" docs/reports/h7_8x_clean_worktree_h8_entry_plan_v0.md

# Content references
grep -nE "git worktree add ../nexus-h8-clean HEAD|NOT EXECUTED IN H7-8X|OWNER APPROVAL REQUIRED|153 passed|H8-0 Controlled Local Model Adapter Reality Map|git restore can discard|git clean can delete|git rm --cached changes" docs/reports/h7_8x_clean_worktree_h8_entry_plan_v0.md

# Git state
git status --short
git diff --cached --name-only
git diff --name-only HEAD
```
