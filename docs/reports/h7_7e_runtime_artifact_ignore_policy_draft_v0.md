# H7-7E Runtime Artifact Ignore Policy Draft v0

**日期**: 2026-06-26  
**狀態**: `H7_7E_RUNTIME_ARTIFACT_IGNORE_POLICY_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `DRAFT_ONLY=true`, `REPORT_ONLY=true`, `READ_ONLY=true`, `IGNORE_FILES_MODIFIED=false`, `NO_FILES_DELETED`, `NO_FILES_MOVED`, `NO_FILES_ARCHIVED`, `NO_FILES_RESTORED`, `NO_GIT_CLEAN`, `NO_GIT_RESTORE`, `NO_RM`, `NO_BENCHMARK_RUN`, `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_MODEL_EXECUTION`, `NO_H7_RUNTIME`, `NO_RECOVERY_RUNTIME`, `NO_RESUME_RUNTIME`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 draft-only / report-only 產出。本任務期間未修改 `.gitignore`、未修改 `.gitnexusignore`、未刪除任何檔案、未執行任何命令。所有規則均為建議，不構成任何實際變更。

---

## 0. Status / Safety Boundary

* **status**: `H7_7E_RUNTIME_ARTIFACT_IGNORE_POLICY_DRAFT_READY_FOR_REVIEW`
* **draft_only=true** (僅草稿)
* **report_only=true** (僅報告)
* **read_only=true** (僅讀取)
* **ignore_files_modified=false** (ignore 檔案未變更)
* **no files deleted** (未刪除檔案)
* **no files moved** (未移動檔案)
* **no files archived** (未封存檔案)
* **no files restored** (未還原檔案)
* **no git clean** (未執行 git clean)
* **no git restore** (未執行 git restore)
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
* **artifacts_accepted_as_evidence=false** (artifacts 未被接受為證據)
* **production_ready=false** (生產就緒為 false)
* **public_claim_allowed=false** (公開宣稱許可為 false)

---

## 1. Scope

* **H7-7E drafts ignore policy only**: 僅草擬 ignore 規則。
* **H7-7E does not apply ignore policy**: 不套用任何 ignore 規則。
* **H7-7E does not modify .gitignore or .gitnexusignore**: 不修改任何 ignore 檔案。
* **H7-7E does not clean artifacts**: 不清理任何 artifacts。
* **H7-7E does not accept artifacts as evidence**: 不宣告任何 artifact 為證據。

---

## 2. Current Ignore State

| File | Contains `artifacts/runtime/**`? | Notes |
| :--- | :--- | :--- |
| `.gitignore` | **NO** | does NOT ignore `artifacts/runtime/**` — this is the root cause of 45 tracked dirty files |
| `.gitnexusignore` | **YES** (`artifacts/**/*`) | GitNexus already ignores all artifacts, but git does not |

**Root cause**: `.gitignore` lacks `artifacts/runtime/**`, so generated runtime outputs are tracked by git. Every new eval run modifies these files, creating permanent dirty-file noise.

---

## 3. Proposed Ignore Rules

### Recommended: Broad ignore for all generated runtime outputs

Add to `.gitignore`:

```gitignore
# Nexus generated runtime artifacts (eval runs, benchmarks, regression results)
# These are generated outputs, not source code or curated evidence.
# Curated evidence should live in docs/reports/ or artifacts/evidence_packs/
artifacts/runtime/**
```

**Why broad**: All files under `artifacts/runtime/` are generated runtime outputs — eval runs, benchmark results, regression evidence, RRL3 bundles. None are source code. None are curated evidence. The entire directory tree is machine-generated.

**Evidence exception**: If curated evidence is needed, it should live outside `artifacts/runtime/`:
- `docs/reports/` — for committed report evidence
- `artifacts/evidence_packs/` — for curated evidence packs (if created)

### Alternative: Narrow ignore (not recommended)

If some tracked runtime artifacts must remain versioned (e.g., baseline benchmarks), narrower rules could be:

```gitignore
# Generated runtime sub-outputs
artifacts/runtime/**/runs/**
artifacts/runtime/**/execution_results/*.json
artifacts/runtime/**/test_*.json
artifacts/runtime/rrl3_runs/**
```

**Why not recommended**: This creates maintenance burden — every new eval substrate directory would need a new rule. The broad rule is simpler and safer.

---

## 4. Tracked File Limitation

**Ignore rules do not affect already tracked files.**

The 45 currently tracked modified runtime artifacts will remain dirty even after adding `artifacts/runtime/**` to `.gitignore`. They require a separate decision:

1. **Restore** (via `git restore`) — revert working-tree changes, keep files tracked
2. **Untrack** (via `git rm --cached`) — remove from index, keep on disk, let `.gitignore` handle future
3. **Keep dirty** — accept ongoing noise until manual cleanup

H7-7D already proposed the restore path. The untrack path (`git rm --cached`) is an alternative that preserves working-tree versions while stopping future tracking.

---

## 5. Evidence Exception Policy

* **Runtime artifacts are not H7 gate evidence.** H7 gate evidence = committed tests + committed reports only.
* **H7 gate evidence remains committed tests and committed reports only.** Specifically: `tests/benchmark/test_h7_*.py` + `docs/reports/h7_*.md`.
* **Future curated evidence must have explicit report/receipt linkage.** No artifact is evidence unless a report explicitly references it.
* **Curated evidence should not live in generated runtime output paths unless owner approves.** Prefer `docs/reports/` or `artifacts/evidence_packs/` for curated evidence.

---

## 6. Recommended Future Task

**H7-8 Workspace Cleanup Approval Plan**

This task should:
1. Present the exact `.gitignore` addition for owner approval
2. Present the exact `git restore` or `git rm --cached` command for 45 tracked artifacts
3. Execute only after explicit owner sign-off

H7-7F (curated evidence commit) is not recommended because no artifact has been identified as having explicit report/receipt linkage. All runtime artifacts appear to be generated noise.

---

## 7. Acceptance Criteria

* [x] Report exists: `docs/reports/h7_7e_runtime_artifact_ignore_policy_draft_v0.md`
* [x] No production code modified
* [x] No tests modified
* [x] No CI modified
* [x] Ignore files not modified
* [x] No files deleted/moved/restored
* [x] No git clean run
* [x] No git restore run
* [x] No benchmark/runtime command run
* [x] Proposed ignore rules documented
* [x] Tracked file limitation documented
* [x] Evidence exception policy documented
* [x] No policy executed
* [x] Final state: `H7_7E_RUNTIME_ARTIFACT_IGNORE_POLICY_DRAFT_READY_FOR_REVIEW`

---

## 8. Final State

`H7_7E_RUNTIME_ARTIFACT_IGNORE_POLICY_DRAFT_READY_FOR_REVIEW`

### Forbidden Final States

* `IGNORE_POLICY_APPLIED`
* `GITIGNORE_MODIFIED`
* `GITNEXUSIGNORE_MODIFIED`
* `ARTIFACTS_DELETED`
* `ARTIFACTS_RESTORED`
* `ARTIFACTS_ARCHIVED`
* `ARTIFACTS_ACCEPTED_AS_EVIDENCE`
* `WORKSPACE_CLEANED`
* `GIT_CLEAN_EXECUTED`
* `GIT_RESTORE_EXECUTED`
* `H7_RUNTIME_ROUTING_ENABLED`
* `PRODUCTION_READY`
* `PUBLIC_CLAIM_ALLOWED`

---

## 9. Verification Commands

```bash
# Report exists
test -f docs/reports/h7_7e_runtime_artifact_ignore_policy_draft_v0.md && echo H7_7E_REPORT_EXISTS

# Safety boundary strings
grep -nE "H7_7E_RUNTIME_ARTIFACT_IGNORE_POLICY_DRAFT_READY_FOR_REVIEW|draft_only=true|report_only=true|read_only=true|ignore_files_modified=false|no files deleted|no files restored|no git clean|no git restore|no benchmark run|workspace_cleaned=false|artifacts_accepted_as_evidence=false|production_ready=false|public_claim_allowed=false" docs/reports/h7_7e_runtime_artifact_ignore_policy_draft_v0.md

# Content references
grep -nE "artifacts/runtime|Ignore rules do not affect already tracked files|H7 gate evidence remains committed tests and committed reports only|curated evidence|H7-7F Curated Evidence Commit Candidate Review|H7-8 Workspace Cleanup Approval Plan|IGNORE_POLICY_APPLIED|GITIGNORE_MODIFIED|GITNEXUSIGNORE_MODIFIED" docs/reports/h7_7e_runtime_artifact_ignore_policy_draft_v0.md

# Git state
git status --short
git diff --cached --name-only
git diff --name-only HEAD
```
