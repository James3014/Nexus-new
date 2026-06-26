# H7-7 Workspace Hygiene / Dirty File Triage v0

**日期**: 2026-06-26  
**狀態**: `H7_7_WORKSPACE_HYGIENE_DIRTY_FILE_TRIAGE_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `READ_ONLY=true`, `NO_FILE_CLEANUP`, `NO_FILE_DELETION`, `NO_GIT_CLEAN`, `NO_GIT_RESTORE`, `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_PROCESS_SPAWN`, `NO_NETWORK_CALL`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 read-only / report-only 產出。本任務期間未清理任何檔案、未刪除任何檔案、未執行 git clean、未執行 git restore、未執行任何 runtime 行為。所有分類均為分析建議，不構成任何自動化操作。

---

## 0. Status / Safety Boundary

* **status**: `H7_7_WORKSPACE_HYGIENE_DIRTY_FILE_TRIAGE_DRAFT_READY_FOR_REVIEW`
* **read_only=true** (僅讀取)
* **no file cleanup** (未清理檔案)
* **no file deletion** (未刪除檔案)
* **no git clean** (未執行 git clean)
* **no git restore** (未執行 git restore)
* **no runtime behavior change** (無執行期行為變更)
* **no provider call** (無 provider 呼叫)
* **no model call** (無模型調用)
* **no network call** (無網路存取)
* **no model load** (無模型載入)
* **no model execution** (無模型執行)
* **no learned policy adoption** (無學習策略採用)
* **no new router** (無新路由器)
* **no checkpoint writer** (無檢查點寫入)
* **no resume CLI** (無恢復/繼續命令列工具)
* **recovery_ready=false** (復原狀態未就緒)
* **resume_ready=false** (繼續狀態未就緒)
* **routing_ready=false** (路由狀態未就緒)
* **production_ready=false** (生產就緒為 false)
* **public_claim_allowed=false** (公開宣稱許可為 false)
* **H7 runtime not started** (H7 執行期尚未啟動)
* **CI not modified** (CI workflows 未變更)
* **CI not enabled** (CI 未啟用)

---

## 1. Scope

* **H7-7 is report-only**: 本報告僅分類 dirty files 並提出建議，不執行任何清理操作。
* **H7-7 does not clean the workspace**: 不刪除、不還原、不清理任何檔案。
* **H7-7 does not decide final deletion/archive policy**: 僅分析分類，最終決策留給 owner。
* **H7-7 only classifies dirty files and proposes safe next actions**: 建立分類矩陣與安全的下一步建議。

---

## 2. Current Git Snapshot

| Item | Value |
| :--- | :--- |
| **HEAD hash** | `064989c914b8c37bcf989388d13c0c4ca74d24fe` |
| **Latest H7 commit** | `064989c9` — `docs: add H7-6 focused test index CI selection plan` |
| **Staged area** | empty |
| **Total dirty files** | 99 |

### Summary by Bucket

| Bucket | Count | Description |
| :--- | :--- | :--- |
| **A. H7 current scope** | 0 | H7-6 committed; H7-7 report not yet on disk at triage time |
| **B. CI / config candidate** | 10 | `.github/workflows/`, `pyproject.toml`, `uv.lock`, F02/F03 reports, hybrid/U3 reports |
| **C. local_heal implementation** | 7 | `nexus/services/local_heal/` production + `tests/unit/local_heal/` tests |
| **D. runtime artifacts** | 46 | `artifacts/runtime/**` modified + untracked runtime data |
| **E. generated cache / pycache** | 23 | `__pycache__/**/*.pyc` across nexus + tests |
| **F. hybrid route / U3 reports** | 4 | `docs/reports/hybrid_*` + `docs/reports/u3_*` |
| **G. scratch / temporary scripts** | 2 | `scratch/run_rerun_eval_8.py`, `scratch/verify_artifacts_eval_8.py` |
| **H. unknown / needs owner decision** | 1 | `.gitnexusignore` |
| **I. local_heal untracked test** | 1 | `tests/unit/local_heal/test_native_route_adapter.py` (untracked) |
| **Total** | **99** | — |

---

## 3. Dirty File Classification Matrix

| Bucket | File / pattern | Status | Why classified here | Risk | Recommended next action | Commit allowed now? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **B** | `.github/workflows/security.yml` | `??` untracked | CI workflow definition — likely new CI gate | High: mixes CI policy with H7 reports | Isolated review in F02/F03 task line | no |
| **B** | `.github/workflows/typecheck.yml` | `??` untracked | CI workflow definition — likely new CI gate | High: mixes CI policy with H7 reports | Isolated review in F02/F03 task line | no |
| **B** | `pyproject.toml` | ` M` modified | Dependency config — likely related to CI/tooling changes | High: changes project-wide build/test config | Needs isolated review; do not mix with H7 | no |
| **B** | `uv.lock` | ` M` modified | Lock file — auto-generated from pyproject.toml changes | Medium: auto-generated but large diff | Commit together with pyproject.toml after review | no |
| **B** | `docs/reports/f02a_scoped_pyright_ci_gate_2026-06-25.md` | `??` untracked | F02 scoped pyright CI gate report | Low: documentation only | Review in F02 task line | no |
| **B** | `docs/reports/f03a_scoped_bandit_ci_gate_2026-06-25.md` | `??` untracked | F03 scoped bandit CI gate report | Low: documentation only | Review in F03 task line | no |
| **C** | `nexus/services/local_heal/backend_resource_policy.py` | ` M` modified | Production code — local_heal resource policy | High: production code change | Isolated validation in local_heal task line | no |
| **C** | `nexus/services/local_heal/interface.py` | ` M` modified | Production code — local_heal interface | High: production code change | Isolated validation in local_heal task line | no |
| **C** | `nexus/services/local_heal/native_route_adapter.py` | ` M` modified | Production code — native route adapter | High: production code change | Isolated validation in local_heal task line | no |
| **C** | `nexus/services/local_heal/phases/patch_synthesis.py` | ` M` modified | Production code — patch synthesis phase | High: production code change | Isolated validation in local_heal task line | no |
| **C** | `nexus/services/local_heal/role_contract.py` | ` M` modified | Production code — role contract | High: production code change | Isolated validation in local_heal task line | no |
| **C** | `tests/unit/local_heal/test_role_contract.py` | ` M` modified | Test code — role contract tests | Medium: test code change | Commit with local_heal production changes | no |
| **C** | `tests/unit/local_heal/test_native_route_adapter.py` | `??` untracked | Test code — native route adapter tests | Medium: new test file | Commit with local_heal production changes | no |
| **D** | `artifacts/runtime/ao2_live_regression_entrypoints_v0/c12481_regression_result.json` | ` M` modified | Runtime regression evidence — C12481 | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **D** | `artifacts/runtime/ao2_live_regression_entrypoints_v0/c13453_regression_result.json` | ` M` modified | Runtime regression evidence — C13453 | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **D** | `artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/*.json` (×11) | ` M` modified | Benchmark execution results — concurrency/protocol | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **D** | `artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs/C_1/nexus_memory_on/*.json` (×11) | ` M` modified | Eval run evidence — C1 memory on | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **D** | `artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs/C_12481/nexus_memory_off/*.json` (×11) | ` M` modified | Eval run evidence — C12481 memory off | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **D** | `artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs/C_12481/nexus_memory_on/*.json` (×11) | ` M` modified | Eval run evidence — C12481 memory on | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **D** | `artifacts/runtime/ao2_live_regression_entrypoints_v0/test_c12481.json` | `??` untracked | Test regression evidence — C12481 | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **D** | `artifacts/runtime/ao2_live_regression_entrypoints_v0/test_c13453.json` | `??` untracked | Test regression evidence — C13453 | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **D** | `artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs/C_1/nexus_memory_off/` | `??` untracked dir | Eval run evidence — C1 memory off (new) | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **D** | `artifacts/runtime/rrl3_runs/` | `??` untracked dir | RRL3 run evidence | Low: evidence artifact | Archive or dedicated evidence commit | no |
| **E** | `nexus/experimental/__pycache__/*.pyc` (×2) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `nexus/research/domain/__pycache__/*.pyc` (×3) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `nexus/rollout/__pycache__/*.pyc` (×2) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `nexus/verifiers/domain/astropy/__pycache__/*.pyc` (×3) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `nexus/verifiers/domain/common_core/__pycache__/*.pyc` (×3) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `nexus/verifiers/domain/concurrency/__pycache__/*.pyc` (×6) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `nexus/verifiers/domain/django/__pycache__/*.pyc` (×2) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `tests/unit/experimental/__pycache__/*.pyc` (×1) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `tests/unit/research/__pycache__/*.pyc` (×1) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `tests/unit/rollout/__pycache__/*.pyc` (×1) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `tests/unit/verifiers/astropy/__pycache__/*.pyc` (×1) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `tests/unit/verifiers/common_core/__pycache__/*.pyc` (×1) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `tests/unit/verifiers/concurrency/__pycache__/*.pyc` (×1) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **E** | `tests/unit/verifiers/django/__pycache__/*.pyc` (×1) | ` M` modified | Bytecode cache — generated noise | None: never commit | Add to .gitignore; cleanup with approval | no |
| **F** | `docs/reports/hybrid_dynamic_route_h0_audit_v0.md` | `??` untracked | Hybrid route H0 audit report | Low: documentation for future H8/H9 | Review in hybrid route task line | no |
| **F** | `docs/reports/hybrid_dynamic_route_integration_point_matrix_v0.json` | `??` untracked | Hybrid route integration matrix | Low: documentation for future H8/H9 | Review in hybrid route task line | no |
| **F** | `docs/reports/hybrid_dynamic_route_mode_schema_draft_v0.json` | `??` untracked | Hybrid route mode schema draft | Low: documentation for future H8/H9 | Review in hybrid route task line | no |
| **F** | `docs/reports/u3_candidate_isolation_preflight_audit_v0.md` | `??` untracked | U3 candidate isolation audit | Low: documentation for future U3 | Review in U3 task line | no |
| **G** | `scratch/run_rerun_eval_8.py` | `??` untracked | Temporary eval rerun script | Low: one-off helper | Owner decision: delete or archive | no |
| **G** | `scratch/verify_artifacts_eval_8.py` | `??` untracked | Temporary artifact verification script | Low: one-off helper | Owner decision: delete or archive | no |
| **H** | `.gitnexusignore` | ` M` modified | GitNexus ignore config — unclear origin | Medium: affects code intelligence indexing | Owner decision: review and commit separately | no |
| **I** | `tests/unit/local_heal/test_native_route_adapter.py` | `??` untracked | New test file — local_heal native route adapter | Medium: new test, relates to bucket C | Commit with local_heal production changes | no |

---

## 4. Cross-contamination Risks

| Risk | Description | Mitigation |
| :--- | :--- | :--- |
| **H7 gate evidence contaminated by unrelated runtime artifacts** | 46 runtime artifact files in `artifacts/runtime/` could be mistaken as H7 gate evidence if committed together | H7 commits must NEVER include `artifacts/runtime/` files; runtime artifacts need separate evidence commits |
| **CI/config changes mixed with H7 report/test commits** | `.github/workflows/`, `pyproject.toml`, `uv.lock` could contaminate H7 commit history if mixed | CI/config changes must be in separate task lines (F02/F03); never mix with H7 reports |
| **local_heal implementation mixed with report-only H7** | 7 local_heal files (5 production + 2 test) represent active implementation work, not H7 planning | local_heal changes need their own focused validation; never mix with H7 report commits |
| **pycache accidentally committed** | 23 `.pyc` files currently tracked as modified — high risk of accidental `git add -p` or bulk staging | Ensure `__pycache__` is in `.gitignore`; cleanup with explicit approval only |
| **runtime artifacts mistaken as accepted benchmark evidence** | `artifacts/runtime/` files look like evidence but may be stale or from failed runs | Treat runtime artifacts as provisional until explicitly verified; never commit as H7 acceptance evidence |
| **U3/hybrid route reports mixed into H7 safe-slice** | 4 U3/hybrid route docs could be committed alongside H7 reports, muddying H7 audit trail | H7 commits must only include `docs/reports/h7_*` files; U3/hybrid docs go to their own task lines |

---

## 5. Recommended Split Plan

| # | Task Line | Scope | Files | Must Not Mix With |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **H7-7A Generated Cache Cleanup Preview** | Preview pycache removal; no deletion without approval | `**/__pycache__/**/*.pyc` (23 files) | Any production/test/CI code |
| **2** | **H7-7B Runtime Artifact Archive/Ignore Decision** | Decide: archive, ignore, or dedicated evidence commit | `artifacts/runtime/**` (46 files) | H7 gate commits, local_heal |
| **3** | **F02/F03 Scoped CI/Config Review** | Review `.github/workflows/`, `pyproject.toml`, `uv.lock`, F02/F03 reports | 6 files | H7 reports, local_heal, runtime artifacts |
| **4** | **local_heal Native Route Adapter Validation** | Validate and commit local_heal implementation + tests | 7 files (`nexus/services/local_heal/**`, `tests/unit/local_heal/**`) | H7 reports, CI/config, runtime artifacts |
| **5** | **U3/Hybrid Route Report Review** | Review and commit hybrid route + U3 audit docs | 4 files (`docs/reports/hybrid_*`, `docs/reports/u3_*`) | H7 reports, CI/config, local_heal |
| **6** | **Scratch Helper Disposition** | Owner decides: delete, archive, or commit | 2 files (`scratch/run_rerun_eval_8.py`, `scratch/verify_artifacts_eval_8.py`) | Everything else |

Each task line must be **separate and must not be mixed** with others.

---

## 6. Immediate Next Recommended Task

### H7-7A Generated Cache Cleanup Preview

**原因**: 23 `.pyc` files are the lowest-risk cleanup target — they are generated noise that should never be committed. Previewing their removal has zero impact on production code, tests, or CI.

**Constraints**:
* preview only first — run `git clean -nd` to list what would be removed
* no deletion without explicit approval
* do not run destructive cleanup in H7-7
* if approval given, run `git clean -n` first, then `git clean -f` only on `__pycache__` directories

---

## 7. Acceptance Criteria

* [x] Report exists: `docs/reports/h7_7_workspace_hygiene_dirty_file_triage_v0.md`
* [x] No production code modified
* [x] No tests modified
* [x] No CI modified
* [x] No files deleted
* [x] No files restored
* [x] No git clean run
* [x] No provider/model/network/model-load/model-call executed
* [x] No runtime route behavior change
* [x] No learned policy adoption
* [x] No checkpoint/resume behavior
* [x] Staged area unchanged (empty)
* [x] All visible dirty file classes categorized (9 buckets)
* [x] Final state: `H7_7_WORKSPACE_HYGIENE_DIRTY_FILE_TRIAGE_DRAFT_READY_FOR_REVIEW`

---

## 8. Final State

`H7_7_WORKSPACE_HYGIENE_DIRTY_FILE_TRIAGE_DRAFT_READY_FOR_REVIEW`

### Forbidden Final States

* `H7_RUNTIME_ROUTING_ENABLED`
* `H7_CAPABILITY_ROUTING_READY`
* `H7_RECOVERY_READY`
* `H7_RESUME_READY`
* `PRODUCTION_READY`
* `PUBLIC_CLAIM_ALLOWED`
* `PROVIDER_READY`
* `MODEL_READY`
* `CI_ENABLED`
* `WORKSPACE_CLEANED`
* `FILES_DELETED`

---

## 9. Verification Commands

```bash
# Report exists
test -f docs/reports/h7_7_workspace_hygiene_dirty_file_triage_v0.md && echo H7_7_REPORT_EXISTS

# Safety boundary strings
grep -nE "H7_7_WORKSPACE_HYGIENE_DIRTY_FILE_TRIAGE_DRAFT_READY_FOR_REVIEW|read_only=true|no file cleanup|no file deletion|no git clean|no git restore|no runtime behavior change|no provider call|no model call|no network call|no model load|no model execution|no learned policy adoption|no new router|no checkpoint writer|no resume CLI|recovery_ready=false|resume_ready=false|routing_ready=false|production_ready=false|public_claim_allowed=false|H7 runtime not started|CI not modified|CI not enabled" docs/reports/h7_7_workspace_hygiene_dirty_file_triage_v0.md

# Bucket references
grep -nE "CI / config candidate|local_heal implementation candidate|runtime artifacts|generated cache|pycache|hybrid route|U3 reports|scratch|unknown|H7-7A Generated Cache Cleanup Preview|WORKSPACE_CLEANED|FILES_DELETED" docs/reports/h7_7_workspace_hygiene_dirty_file_triage_v0.md

# Git state
git status --short
git diff --cached --name-only
git diff --name-only HEAD
```
