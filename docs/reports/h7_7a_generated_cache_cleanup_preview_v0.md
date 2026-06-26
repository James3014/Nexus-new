# H7-7A Generated Cache Cleanup Preview v0

**日期**: 2026-06-26  
**狀態**: `H7_7A_GENERATED_CACHE_CLEANUP_PREVIEW_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `PREVIEW_ONLY=true`, `READ_ONLY=true`, `NO_FILES_DELETED`, `NO_FILE_CLEANUP`, `NO_GIT_CLEAN_F`, `NO_GIT_RESTORE`, `NO_RM`, `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_PROCESS_SPAWN`, `NO_NETWORK_CALL`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 preview-only / read-only 產出。本任務期間未刪除任何檔案、未清理任何檔案、未執行 git clean -f、未執行 git restore。所有命令均為 dry-run 或只讀查詢。

---

## 0. Status / Safety Boundary

* **status**: `H7_7A_GENERATED_CACHE_CLEANUP_PREVIEW_DRAFT_READY_FOR_REVIEW`
* **preview_only=true** (僅預覽)
* **read_only=true** (僅讀取)
* **no files deleted** (未刪除檔案)
* **no file cleanup** (未清理檔案)
* **no git clean -f** (未執行強制清理)
* **no git restore** (未執行還原)
* **no rm** (未執行刪除)
* **no production code modified** (未修改生產代碼)
* **no tests modified** (未修改測試)
* **no CI modified** (未修改 CI)
* **workspace_cleaned=false** (工作區未清理)
* **runtime behavior changed=false** (無執行期行為變更)
* **provider_model_network_executed=false** (未執行 provider/model/network)
* **H7 runtime not started** (H7 執行期尚未啟動)
* **production_ready=false** (生產就緒為 false)
* **public_claim_allowed=false** (公開宣稱許可為 false)

---

## 1. Scope

* **H7-7A is preview-only**: 本報告僅識別 generated cache files 並提出清理建議。
* **H7-7A does not clean files**: 不清理任何檔案。
* **H7-7A does not delete files**: 不刪除任何檔案。
* **H7-7A only identifies generated cache files and proposes cleanup commands for later approval**: 建立 inventory 與 cleanup plan，留待 owner 批准後執行。

---

## 2. Cache File Inventory

### 2.1 Dirty Tracked Cache Files

所有 30 個 pycache 檔案均為 **tracked + modified** 狀態（` M`），表示它們曾被 commit 過，但目前 working tree 版本與 index 不同。

| File | Git status | Category | Safe to clean later? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `nexus/experimental/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/experimental/__pycache__/sandboxed_adapter.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/research/domain/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/research/domain/__pycache__/route_planner.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/research/domain/__pycache__/routing_receipt.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/rollout/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/rollout/__pycache__/canary_guard.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/astropy/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/astropy/__pycache__/astrophysics_guard.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/astropy/__pycache__/fits_reader.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/common_core/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/common_core/__pycache__/lock_helpers.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/common_core/__pycache__/state_guards.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/concurrency/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/concurrency/__pycache__/buggy_targets.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/concurrency/__pycache__/buggy_targets_batch_b01.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/concurrency/__pycache__/buggy_targets_batch_b02.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/concurrency/__pycache__/fixed_targets.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/concurrency/__pycache__/fixed_targets_batch_b01.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/concurrency/__pycache__/fixed_targets_batch_b02.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/django/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/django/__pycache__/django_core_logic_guard.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `nexus/verifiers/domain/django/__pycache__/django_migration_guard.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `tests/unit/experimental/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `tests/unit/research/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `tests/unit/rollout/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `tests/unit/verifiers/astropy/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `tests/unit/verifiers/common_core/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `tests/unit/verifiers/concurrency/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |
| `tests/unit/verifiers/django/__pycache__/__init__.cpython-314.pyc` | ` M` | tracked modified | yes (with restore) | requires `git restore` |

**Count**: 30 tracked modified `.pyc` files

### 2.2 Untracked Cache Files

**None.** No untracked `.pyc` or `__pycache__` files detected.

---

## 3. Cleanup Preview

### Preview command used:

```bash
git clean -nd -- '**/__pycache__' '*.pyc'
```

### Output:

```
(no output)
```

### Explanation:

`git clean` only operates on **untracked files**. Since all 30 `.pyc` files are **tracked** (they exist in the git index), `git clean` sees nothing to remove. This is the expected behavior — the pycache files were accidentally committed to the repository at some point, and `git clean` cannot help with tracked file hygiene.

---

## 4. Proposed Cleanup Plan for Later Approval

### Step 1: Restore tracked modified `.pyc` files (requires owner approval)

All 30 tracked `.pyc` files need explicit `git restore` to revert them to their committed state:

```bash
git restore \
  nexus/experimental/__pycache__/__init__.cpython-314.pyc \
  nexus/experimental/__pycache__/sandboxed_adapter.cpython-314.pyc \
  nexus/research/domain/__pycache__/__init__.cpython-314.pyc \
  nexus/research/domain/__pycache__/route_planner.cpython-314.pyc \
  nexus/research/domain/__pycache__/routing_receipt.cpython-314.pyc \
  nexus/rollout/__pycache__/__init__.cpython-314.pyc \
  nexus/rollout/__pycache__/canary_guard.cpython-314.pyc \
  nexus/verifiers/domain/astropy/__pycache__/__init__.cpython-314.pyc \
  nexus/verifiers/domain/astropy/__pycache__/astrophysics_guard.cpython-314.pyc \
  nexus/verifiers/domain/astropy/__pycache__/fits_reader.cpython-314.pyc \
  nexus/verifiers/domain/common_core/__pycache__/__init__.cpython-314.pyc \
  nexus/verifiers/domain/common_core/__pycache__/lock_helpers.cpython-314.pyc \
  nexus/verifiers/domain/common_core/__pycache__/state_guards.cpython-314.pyc \
  nexus/verifiers/domain/concurrency/__pycache__/__init__.cpython-314.pyc \
  nexus/verifiers/domain/concurrency/__pycache__/buggy_targets.cpython-314.pyc \
  nexus/verifiers/domain/concurrency/__pycache__/buggy_targets_batch_b01.cpython-314.pyc \
  nexus/verifiers/domain/concurrency/__pycache__/buggy_targets_batch_b02.cpython-314.pyc \
  nexus/verifiers/domain/concurrency/__pycache__/fixed_targets.cpython-314.pyc \
  nexus/verifiers/domain/concurrency/__pycache__/fixed_targets_batch_b01.cpython-314.pyc \
  nexus/verifiers/domain/concurrency/__pycache__/fixed_targets_batch_b02.cpython-314.pyc \
  nexus/verifiers/domain/django/__pycache__/__init__.cpython-314.pyc \
  nexus/verifiers/domain/django/__pycache__/django_core_logic_guard.cpython-314.pyc \
  nexus/verifiers/domain/django/__pycache__/django_migration_guard.cpython-314.pyc \
  tests/unit/experimental/__pycache__/__init__.cpython-314.pyc \
  tests/unit/research/__pycache__/__init__.cpython-314.pyc \
  tests/unit/rollout/__pycache__/__init__.cpython-314.pyc \
  tests/unit/verifiers/astropy/__pycache__/__init__.cpython-314.pyc \
  tests/unit/verifiers/common_core/__pycache__/__init__.cpython-314.pyc \
  tests/unit/verifiers/concurrency/__pycache__/__init__.cpython-314.pyc \
  tests/unit/verifiers/django/__pycache__/__init__.cpython-314.pyc
```

**Note**: This only reverts the dirty working-tree changes. The files remain tracked in the index. To fully remove them from tracking, a separate `git rm --cached` commit would be needed (not proposed in H7-7A).

### Step 2: Add `__pycache__/` to `.gitignore` (separate task)

After restoring, ensure `__pycache__/` is in `.gitignore` to prevent future accidental staging. This is a separate configuration task, not part of H7-7A.

### Step 3: For any future untracked pycache (if generated after restore)

```bash
git clean -f -- '**/__pycache__' '*.pyc'
```

This would only affect untracked cache files generated after the restore.

---

## 5. Risk Notes

| Risk | Detail | Mitigation |
| :--- | :--- | :--- |
| `git clean` does not affect tracked modified `.pyc` files | All 30 current dirty pycache files are tracked — `git clean` sees nothing to remove | Must use `git restore` for tracked files |
| tracked `.pyc` files are repository hygiene debt | 30 `.pyc` files were committed to the repo, creating ongoing dirty-file noise | Full cleanup requires `git rm --cached` + `.gitignore` update (separate task) |
| deleting/restoring generated files requires owner approval | Even preview commands must not auto-execute destructive operations | H7-7A proposes only; owner must explicitly approve |
| do not mix cache cleanup with H7 reports, CI config, local_heal, runtime artifacts, or U3/hybrid reports | Cache cleanup is an isolated hygiene task | Keep cache cleanup in its own commit; never bundle with other changes |

---

## 6. Acceptance Criteria

* [x] Report exists: `docs/reports/h7_7a_generated_cache_cleanup_preview_v0.md`
* [x] No production code modified
* [x] No tests modified
* [x] No CI modified
* [x] No files deleted
* [x] No files restored
* [x] No destructive git clean run
* [x] Only preview commands executed
* [x] Cache files inventoried (30 tracked modified, 0 untracked)
* [x] Cleanup commands proposed but not executed
* [x] Unrelated dirty files excluded
* [x] Final state: `H7_7A_GENERATED_CACHE_CLEANUP_PREVIEW_DRAFT_READY_FOR_REVIEW`

---

## 7. Recommended Next Task

### H7-7B Runtime Artifact Archive / Ignore Decision

**原因**: After cache hygiene is resolved, the next largest dirty-file bucket is runtime artifacts (46 files in `artifacts/runtime/`). These need a decision: archive, ignore, or dedicated evidence commit.

**Important**: Actual cache deletion/restoration should only happen with explicit owner approval. H7-7A recommends the commands but does not execute them.

---

## 8. Final State

`H7_7A_GENERATED_CACHE_CLEANUP_PREVIEW_DRAFT_READY_FOR_REVIEW`

### Forbidden Final States

* `WORKSPACE_CLEANED`
* `FILES_DELETED`
* `CACHE_CLEANED`
* `GIT_CLEAN_EXECUTED`
* `GIT_RESTORE_EXECUTED`
* `PRODUCTION_READY`
* `PUBLIC_CLAIM_ALLOWED`
* `H7_RUNTIME_ROUTING_ENABLED`

---

## 9. Verification Commands

```bash
# Report exists
test -f docs/reports/h7_7a_generated_cache_cleanup_preview_v0.md && echo H7_7A_REPORT_EXISTS

# Safety boundary strings
grep -nE "H7_7A_GENERATED_CACHE_CLEANUP_PREVIEW_DRAFT_READY_FOR_REVIEW|preview_only=true|read_only=true|no files deleted|no file cleanup|no git clean -f|no git restore|no rm|no production code modified|no tests modified|no CI modified|workspace_cleaned=false|runtime behavior changed=false|provider_model_network_executed=false|H7 runtime not started|production_ready=false|public_claim_allowed=false" docs/reports/h7_7a_generated_cache_cleanup_preview_v0.md

# Content references
grep -nE "Dirty tracked cache files|Untracked cache files|git clean -nd|git clean -f|git restore|H7-7B Runtime Artifact Archive|WORKSPACE_CLEANED|FILES_DELETED|CACHE_CLEANED|GIT_CLEAN_EXECUTED|GIT_RESTORE_EXECUTED" docs/reports/h7_7a_generated_cache_cleanup_preview_v0.md

# Git state
git status --short
git diff --cached --name-only
git diff --name-only HEAD
```
