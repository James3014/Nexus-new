# H7-8 Workspace Cleanup Approval Plan v0

**日期**: 2026-06-26  
**狀態**: `H7_8_WORKSPACE_CLEANUP_APPROVAL_PLAN_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `APPROVAL_PLAN_ONLY=true`, `REPORT_ONLY=true`, `READ_ONLY=true`, `IGNORE_FILES_MODIFIED=false`, `NO_FILES_DELETED`, `NO_FILES_MOVED`, `NO_FILES_ARCHIVED`, `NO_FILES_RESTORED`, `NO_GIT_CLEAN`, `NO_GIT_RESTORE_EXECUTED`, `NO_GIT_RM_EXECUTED`, `NO_RM`, `NO_BENCHMARK_RUN`, `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_MODEL_EXECUTION`, `NO_H7_RUNTIME`, `NO_RECOVERY_RUNTIME`, `NO_RESUME_RUNTIME`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 approval-plan-only / report-only 產出。本任務期間未修改任何 ignore 檔案、未刪除任何檔案、未還原任何檔案、未執行任何 cleanup 命令。所有命令均為未來候選，等待 owner 批准。

---

## 0. Status / Safety Boundary

* **status**: `H7_8_WORKSPACE_CLEANUP_APPROVAL_PLAN_DRAFT_READY_FOR_REVIEW`
* **approval_plan_only=true** (僅批准計畫)
* **report_only=true** (僅報告)
* **read_only=true** (僅讀取)
* **ignore_files_modified=false** (ignore 檔案未變更)
* **no files deleted** (未刪除檔案)
* **no files moved** (未移動檔案)
* **no files archived** (未封存檔案)
* **no files restored** (未還原檔案)
* **no git clean** (未執行 git clean)
* **no git restore executed** (未執行 git restore)
* **no git rm executed** (未執行 git rm)
* **no rm** (未執行刪除)
* **no benchmark run** (未執行 benchmark)
* **no runtime behavior change** (無執行期行為變更)
* **no provider call** (無 provider 呼叫)
* **no model call** (無模型調用)
* **no network call** (無網路存取)
* **no model load** (無模型載入)
* **no model execution** (無模型執行)
* **no H7 runtime** (H7 執行期未啟動)
* **no recovery runtime** (復原執行期未啟動)
* **no resume runtime** (繼續執行期未啟動)
* **no production code modified** (未修改生產代碼)
* **no tests modified** (未修改測試)
* **no CI modified** (未修改 CI)
* **workspace_cleaned=false** (工作區未清理)
* **artifacts_restored=false** (artifacts 未還原)
* **cache_restored=false** (cache 未還原)
* **tracked_generated_untracked=false** (tracked generated 未 untrack)
* **artifacts_accepted_as_evidence=false** (artifacts 未被接受為證據)
* **production_ready=false** (生產就緒為 false)
* **public_claim_allowed=false** (公開宣稱許可為 false)

---

## 1. Scope

* **H7-8 is approval-plan-only**: 僅提供 owner 批准用的完整計畫。
* **H7-8 does not execute cleanup**: 不執行任何 cleanup。
* **H7-8 consolidates H7-7A through H7-7E**: 整合所有先前 preview/policy 報告。
* **H7-8 prepares exact commands for future owner approval**: 提供精確命令等待批准。
* **H7-8 does not make Nexus runtime ready**: 不使 Nexus runtime 就緒。

---

## 2. Current Dirty Generated Inventory

### 2.1 Tracked Modified Cache Files

* **Count**: 30
* **Files**: `nexus/**/__pycache__/*.pyc`, `tests/**/__pycache__/*.pyc`
* **Proposed policy**: `RESTORE_TRACKED_CACHE`
* **Execution now**: no

### 2.2 Tracked Modified Runtime Artifacts

* **Count**: 45
* **Files**: `artifacts/runtime/ao2_live_regression_entrypoints_v0/*.json`, `artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/*.json`, `artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs/**/*.json`
* **Proposed policy**: `RESTORE_TRACKED_RUNTIME_ARTIFACTS`
* **Execution now**: no

### 2.3 Untracked Runtime Artifacts

* **Count**: 37
* **Files**: `artifacts/runtime/ao2_live_regression_entrypoints_v0/test_*.json`, `artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs/C_1/nexus_memory_off/*.json`, `artifacts/runtime/rrl3_runs/**/*.json`
* **Proposed policy**: `IGNORE_GENERATED_RUNTIME_OUTPUTS`
* **Execution now**: no

### 2.4 Files NOT Included

| Category | Files | Reason excluded |
| :--- | :--- | :--- |
| CI/config | `.github/workflows/security.yml`, `.github/workflows/typecheck.yml` | separate F02/F03 track |
| Dependencies | `pyproject.toml`, `uv.lock` | separate dependency track |
| F02/F03 reports | `docs/reports/f02a_*.md`, `docs/reports/f03a_*.md` | separate CI gate track |
| local_heal | `nexus/services/local_heal/**`, `tests/unit/local_heal/**` | separate implementation track |
| U3/hybrid reports | `docs/reports/hybrid_*`, `docs/reports/u3_*` | separate report track |
| scratch | `scratch/run_rerun_eval_8.py`, `scratch/verify_artifacts_eval_8.py` | separate scratch disposition |
| Config | `.gitnexusignore` | already ignores `artifacts/**/*` |

---

## 3. Proposed Ignore Additions

### For `.gitignore`:

```gitignore
# Nexus generated runtime outputs (eval runs, benchmarks, regression results)
artifacts/runtime/**
# Python bytecode / cache
__pycache__/
*.py[cod]
*$py.class
```

### For `.gitnexusignore`:

Already contains `artifacts/**/*` — no change needed.

**Must state**: Ignore rules do not affect already tracked files.

---

## 4. Proposed Future Restore Commands

> **NOT EXECUTED IN H7-8**  
> **OWNER APPROVAL REQUIRED**

### 4.1 Restore Tracked Modified Runtime Artifacts

```bash
git ls-files --modified artifacts/runtime > /tmp/h7_restore_runtime_artifacts.txt
git restore --pathspec-from-file=/tmp/h7_restore_runtime_artifacts.txt
```

### 4.2 Restore Tracked Modified .pyc Files

```bash
git ls-files --modified | grep -E '(__pycache__|\\.pyc$)' > /tmp/h7_restore_tracked_pyc.txt
git restore --pathspec-from-file=/tmp/h7_restore_tracked_pyc.txt
```

---

## 5. Proposed Future Untrack Commands

> **NOT EXECUTED IN H7-8**  
> **OWNER APPROVAL REQUIRED**

### For tracked generated .pyc files:

```bash
git ls-files | grep -E '(__pycache__|\\.pyc$)' > /tmp/h7_untrack_pyc.txt
git rm --cached --pathspec-from-file=/tmp/h7_untrack_pyc.txt
```

### For tracked runtime artifacts (if owner prefers untrack over restore):

```bash
git ls-files artifacts/runtime > /tmp/h7_untrack_runtime_artifacts.txt
git rm --cached --pathspec-from-file=/tmp/h7_untrack_runtime_artifacts.txt
```

**Must state**:
* `git rm --cached` changes index only.
* It must be followed by explicit commit.
* It must not be mixed with runtime implementation commits.

---

## 6. Proposed Future Verification Sequence

After owner-approved cleanup, future task should run:

```bash
git status --short
git diff --cached --name-only
python3 -m pytest \
  tests/benchmark/test_h7_capability_receipt_denial_fields.py \
  tests/benchmark/test_h7_public_claim_evidence_linkage.py \
  tests/benchmark/test_h7_route_receipt_schema_consistency.py \
  tests/benchmark/test_h7_route_truth_protection.py \
  tests/benchmark/test_h7_recovery_readiness_blockers.py \
  -q
```

**Expected H7 gate count**: 153 passed

---

## 7. Recommended Execution Split After Approval

Do not execute now. Recommend future split:

| # | Task | Scope | Must Not Mix With |
| :--- | :--- | :--- | :--- |
| **1** | **H7-8A Apply Ignore Policy** | only `.gitignore` / `.gitnexusignore` | runtime artifacts, pycache, local_heal |
| **2** | **H7-8B Restore Tracked Generated Runtime Artifacts** | only tracked runtime artifacts | pycache, CI, local_heal |
| **3** | **H7-8C Restore Tracked Python Cache** | only tracked .pyc | runtime artifacts, CI, local_heal |
| **4** | **H7-8D Untrack Generated Files** | only if owner approves removing tracked generated files from index | runtime artifacts, pycache, CI, local_heal |
| **5** | **H7-8E H7 Gate Re-run After Cleanup** | rerun 153 focused tests | everything else |

---

## 8. Why This Accelerates Nexus Runtime

Once generated dirt is isolated, H8 can start controlled local model adapter dry-run without contaminated evidence. Cleanup approval is a blocker for trustworthy runtime evidence, not a detour. H7-8 does not make runtime ready, but it removes the workspace blocker.

---

## 9. Acceptance Criteria

* [x] Report exists: `docs/reports/h7_8_workspace_cleanup_approval_plan_v0.md`
* [x] No production code modified
* [x] No tests modified
* [x] No CI modified
* [x] Ignore files not modified
* [x] No files deleted/moved/restored
* [x] No git clean run
* [x] No git restore run
* [x] No git rm run
* [x] No benchmark/runtime command run
* [x] Proposed ignore additions documented
* [x] Proposed restore commands documented
* [x] Proposed untrack commands documented
* [x] Execution split documented
* [x] No policy executed
* [x] Final state: `H7_8_WORKSPACE_CLEANUP_APPROVAL_PLAN_DRAFT_READY_FOR_REVIEW`

---

## 10. Final State

`H7_8_WORKSPACE_CLEANUP_APPROVAL_PLAN_DRAFT_READY_FOR_REVIEW`

### Forbidden Final States

* `WORKSPACE_CLEANED`
* `IGNORE_POLICY_APPLIED`
* `GITIGNORE_MODIFIED`
* `GITNEXUSIGNORE_MODIFIED`
* `ARTIFACTS_RESTORED`
* `CACHE_RESTORED`
* `TRACKED_GENERATED_UNTRACKED`
* `GIT_CLEAN_EXECUTED`
* `GIT_RESTORE_EXECUTED`
* `GIT_RM_EXECUTED`
* `H7_RUNTIME_ROUTING_ENABLED`
* `PRODUCTION_READY`
* `PUBLIC_CLAIM_ALLOWED`

---

## 11. Verification Commands

```bash
# Report exists
test -f docs/reports/h7_8_workspace_cleanup_approval_plan_v0.md && echo H7_8_REPORT_EXISTS

# Safety boundary strings
grep -nE "H7_8_WORKSPACE_CLEANUP_APPROVAL_PLAN_DRAFT_READY_FOR_REVIEW|approval_plan_only=true|report_only=true|read_only=true|ignore_files_modified=false|no files deleted|no files restored|no git clean|no git restore executed|no git rm executed|workspace_cleaned=false|artifacts_restored=false|cache_restored=false|tracked_generated_untracked=false|production_ready=false|public_claim_allowed=false" docs/reports/h7_8_workspace_cleanup_approval_plan_v0.md

# Content references
grep -nE "artifacts/runtime|__pycache__|Ignore rules do not affect already tracked files|NOT EXECUTED IN H7-8|OWNER APPROVAL REQUIRED|git restore --pathspec-from-file|git rm --cached|153 passed|H7-8A Apply Ignore Policy|H7-8B Restore Tracked Generated Runtime Artifacts|H7-8C Restore Tracked Python Cache|H7-8D Untrack Generated Files|H7-8E H7 Gate Re-run After Cleanup" docs/reports/h7_8_workspace_cleanup_approval_plan_v0.md

# Git state
git status --short
git diff --cached --name-only
git diff --name-only HEAD
```
