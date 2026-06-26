# H7-6 Focused Test Index + CI Selection Plan v0

**日期**: 2026-06-26  
**狀態**: `H7_6_FOCUSED_TEST_INDEX_CI_SELECTION_PLAN_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_PROCESS_SPAWN`, `NO_NETWORK_CALL`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 report-only / command-index-only 產出。本任務期間未啟用任何 runtime routing behavior、未啟用 learned policy、未啟動 provider/model/network/model-load/model-call、未修改任何 production code、未修改任何 tests、未修改任何 CI workflows。H7 仍處於 planning-only 階段。

---

## 0. Status / Safety Boundary

本報告嚴格遵守且驗證以下安全防禦邊界：

* **status**: `H7_6_FOCUSED_TEST_INDEX_CI_SELECTION_PLAN_DRAFT_READY_FOR_REVIEW`
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

* **H7-6 is report-only**: 本報告僅定義穩定的本地/CI 候選指令集，不包含任何執行期程式。
* **H7-6 does not modify tests**: 不修改任何 `tests/**/*.py`。
* **H7-6 does not modify production code**: 不修改任何 `nexus/**/*.py`。
* **H7-6 does not modify CI**: 不修改任何 `.github/workflows/*.yml`。
* **H7-6 only defines a stable local/CI candidate command set**: 僅建立可重複執行的測試選擇器。
* **H7-6 closes command selection, not runtime readiness**: 完成指令選擇，不涉及執行期就緒判定。

---

## 2. Focused Test Index

| Group | Test file | Gate coverage | Expected tests | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **H7-5A** | `tests/benchmark/test_h7_capability_receipt_denial_fields.py` | TG-06 | 30 | Provider/model/network denial field validation |
| **H7-5B** | `tests/benchmark/test_h7_public_claim_evidence_linkage.py` | TG-04, TG-05 | 37 | Public claim safe fail-closed + evidence refs linkage |
| **H7-5C** | `tests/benchmark/test_h7_route_receipt_schema_consistency.py` | TG-01, TG-02, TG-03 | 67 | RouteDecision/CapabilityReceipt/SkillReceipt schema consistency |
| **H7-5D** | `tests/benchmark/test_h7_route_truth_protection.py` | TG-08, TG-09 | 9 | AutonomicRouter isolation + learning policy override prevention |
| **H7-5E** | `tests/benchmark/test_h7_recovery_readiness_blockers.py` | TG-07 | 10 | Recovery readiness blocker validation |
| **Total** | — | TG-01 through TG-09 | **153** | Combined H7 safe-slice gate |

**Observed combined count**: 153 tests (matches expected).

---

## 3. Stable Local Command

```bash
python3 -m pytest \
  tests/benchmark/test_h7_capability_receipt_denial_fields.py \
  tests/benchmark/test_h7_public_claim_evidence_linkage.py \
  tests/benchmark/test_h7_route_receipt_schema_consistency.py \
  tests/benchmark/test_h7_route_truth_protection.py \
  tests/benchmark/test_h7_recovery_readiness_blockers.py \
  -q
```

**Observed result**: `153 passed in 0.59s`

---

## 4. Stable Collect-only Selector

```bash
python3 -m pytest tests/benchmark \
  -k "h7_5a or h7_5b or h7_5c or h7_5d or h7_5e or capability_receipt_denial or public_claim_evidence or route_receipt_schema or route_truth_protection or recovery_readiness" \
  --collect-only -q
```

**Observed result**: `153/1933 tests collected (1780 deselected)`

| Metric | Count |
| :--- | :--- |
| Total tests in `tests/benchmark` | 1933 |
| Selected by H7 selector | 153 |
| Deselected | 1780 |

---

## 5. CI Selection Plan

### CI Stage Definition

| Field | Value |
| :--- | :--- |
| **CI stage name** | `h7-safe-slice` |
| **Trigger** | manual / local first |
| **Future CI command** | same stable local command (see §3) |
| **Required condition before CI** | workspace cleanup or isolated worktree |
| **Required condition before merge gate** | no unrelated dirty artifacts |
| **Required condition before runtime** | H7 runtime remains disabled until separate approval |

### Implementation Status

* **NOT implemented in this report.** H7-6 defines the plan only.
* No `.github/workflows` files were created or modified.
* No CI triggers were enabled.
* No merge gates were configured.

---

## 6. Do Not Broaden Yet

The following are explicitly excluded from the H7 gate scope:

* Do not run all `tests/benchmark` as H7 gate yet — the selector is deliberately narrow.
* Do not include unrelated `local_heal` dirty files (`nexus/services/local_heal/*.py`, `tests/unit/local_heal/*.py`).
* Do not include `artifacts/runtime/` files.
* Do not include `__pycache__/` files.
* Do not include hybrid route draft files (`docs/reports/hybrid_dynamic_route_*.json`, `docs/reports/hybrid_dynamic_route_*.md`).
* Do not modify `.github/workflows/` in H7-6.

---

## 7. Acceptance Criteria

* [x] Report exists: `docs/reports/h7_6_focused_test_index_ci_selection_plan_v0.md`
* [x] No production code modified
* [x] No tests modified
* [x] No CI modified
* [x] No provider/model/network/model-load/model-call executed
* [x] No runtime route behavior change
* [x] No learned policy adoption
* [x] No checkpoint/resume behavior
* [x] H7 focused gate command defined (§3)
* [x] Collect-only selector defined (§4)
* [x] Observed selected count recorded: 153
* [x] Unrelated dirty files excluded
* [x] Final state: `H7_6_FOCUSED_TEST_INDEX_CI_SELECTION_PLAN_DRAFT_READY_FOR_REVIEW`

---

## 8. Recommended Next Task

### H7-7 Workspace Hygiene / Dirty File Triage for H7 Gate Isolation

**原因**: Before enabling CI or runtime work, the repo has unrelated dirty files that should be classified or isolated so H7 gate evidence is not contaminated. Current dirty files include:

* `nexus/services/local_heal/` — modified production code (unrelated to H7 gate)
* `tests/unit/local_heal/` — modified test code (unrelated to H7 gate)
* `pyproject.toml`, `uv.lock` — dependency changes (unrelated to H7 gate)
* `.gitnexusignore` — config change (unrelated to H7 gate)
* `artifacts/runtime/` — runtime artifacts (unrelated to H7 gate)
* `__pycache__/` — bytecode cache (should be gitignored)
* `scratch/` — temporary scripts (should be gitignored)
* Various untracked `docs/reports/` — other report drafts

**H7-7 must remain read-only/report-only unless explicitly approved.**

---

## 9. Final State

`H7_6_FOCUSED_TEST_INDEX_CI_SELECTION_PLAN_DRAFT_READY_FOR_REVIEW`

### Forbidden Final States

The following states are explicitly forbidden at this stage:

* `H7_RUNTIME_ROUTING_ENABLED`
* `H7_CAPABILITY_ROUTING_READY`
* `H7_RECOVERY_READY`
* `H7_RESUME_READY`
* `PRODUCTION_READY`
* `PUBLIC_CLAIM_ALLOWED`
* `PROVIDER_READY`
* `MODEL_READY`
* `CI_ENABLED`

---

## 10. Verification Commands

```bash
# Report exists
test -f docs/reports/h7_6_focused_test_index_ci_selection_plan_v0.md && echo H7_6_REPORT_EXISTS

# Safety boundary strings
grep -nE "H7_6_FOCUSED_TEST_INDEX_CI_SELECTION_PLAN_DRAFT_READY_FOR_REVIEW|no runtime behavior change|no provider call|no model call|no network call|no model load|no model execution|no learned policy adoption|no new router|no checkpoint writer|no resume CLI|recovery_ready=false|resume_ready=false|routing_ready=false|production_ready=false|public_claim_allowed=false|H7 runtime not started|CI not modified|CI not enabled" docs/reports/h7_6_focused_test_index_ci_selection_plan_v0.md

# Test file references and counts
grep -nE "test_h7_capability_receipt_denial_fields.py|test_h7_public_claim_evidence_linkage.py|test_h7_route_receipt_schema_consistency.py|test_h7_route_truth_protection.py|test_h7_recovery_readiness_blockers.py|153 tests|153 selected|h7-safe-slice|H7-7 Workspace Hygiene" docs/reports/h7_6_focused_test_index_ci_selection_plan_v0.md

# Git state
git status --short
git diff --cached --name-only
git diff --name-only HEAD
```
