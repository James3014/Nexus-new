# H8-0 Controlled Local Model Adapter Reality Map v0

**日期**: 2026-06-26  
**狀態**: `H8_0_CONTROLLED_LOCAL_MODEL_ADAPTER_REALITY_MAP_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `REPORT_ONLY=true`, `READ_ONLY=true`, `NO_LOCAL_MODEL_RUN`, `NO_OLLAMA_CALL`, `NO_QWEN_CALL`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_MODEL_EXECUTION`, `NO_H8_RUNTIME`, `NO_RUNTIME_ROUTING_ENABLED`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 report-only / read-only 產出。本任務期間未啟用任何 runtime、未呼叫任何 local model/provider、未修改任何 production code。所有分析均為靜態代碼檢視。

---

## 0. Status / Safety Boundary

* **status**: `H8_0_CONTROLLED_LOCAL_MODEL_ADAPTER_REALITY_MAP_DRAFT_READY_FOR_REVIEW`
* **report_only=true** (僅報告)
* **read_only=true** (僅讀取)
* **no production code modified** (未修改生產代碼)
* **no tests modified** (未修改測試)
* **no CI modified** (未修改 CI)
* **no worktree created** (未建立 worktree)
* **no files deleted** (未刪除檔案)
* **no files restored** (未還原檔案)
* **no git clean** (未執行 git clean)
* **no git restore** (未執行 git restore)
* **no git rm** (未執行 git rm)
* **no local model run** (未執行 local model)
* **no Ollama call** (未呼叫 Ollama)
* **no Qwen call** (未呼叫 Qwen)
* **no provider call** (無 provider 呼叫)
* **no model call** (無模型調用)
* **no network call** (無網路存取)
* **no model load** (無模型載入)
* **no model execution** (無模型執行)
* **no H8 runtime** (H8 執行期未啟動)
* **no runtime routing enabled** (無執行期路由啟用)
* **no recovery runtime** (復原執行期未啟動)
* **no resume runtime** (繼續執行期未啟動)
* **local_model_ready=false** (local model 未就緒)
* **provider_ready=false** (provider 未就緒)
* **model_ready=false** (model 未就緒)
* **routing_ready=false** (路由未就緒)
* **production_ready=false** (生產就緒為 false)
* **public_claim_allowed=false** (公開宣稱許可為 false)

---

## 1. Scope

* **H8-0 is reality map only**: 僅繪製 local model adapter 的現實地圖。
* **H8-0 does not implement adapter**: 不實作 adapter。
* **H8-0 does not enable runtime**: 不啟用 runtime。
* **H8-0 does not call local models**: 不呼叫任何 local model。
* **H8-0 prepares H8-1 test-only seam assertions**: 為 H8-1 的 test-only seam assertions 做準備。

---

## 2. Current H8 Base

| Item | Value |
| :--- | :--- |
| **Current HEAD** | `b55430ee` — `docs: add H7-8X clean worktree H8 entry plan` |
| **H7-8X commit status** | committed |
| **Staged area** | empty |
| **Dirty workspace** | yes — 99 dirty files (local_heal, runtime artifacts, pycache, CI/config) |
| **Clean worktree** | planned, not created |
| **H7 focused gate** | 153 passed in 0.54s |

---

## 3. Candidate Local Model Adapter Touchpoints

| File/module | Current status | Why relevant | Dirty or committed? | Risk | H8 action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `nexus/engine/local_model_policy.py` | committed | ModelProfile class — Ollama/Qwen config, temperature, context sizing | committed | low: already in repo | review for H8-1 seams |
| `nexus/services/local_heal/native_route_adapter.py` | **dirty** | B1-A native route decision — explicit route profile for qwen_3b/7b/deepseek_6_7b | dirty (M) | high: not safe H8 base | review separately before H8 |
| `nexus/services/local_heal/backend_resource_policy.py` | **dirty** | Resource policy — backend resource constraints | dirty (M) | high: not safe H8 base | review separately before H8 |
| `nexus/services/local_heal/interface.py` | **dirty** | Local heal interface | dirty (M) | high: not safe H8 base | review separately before H8 |
| `nexus/services/local_heal/role_contract.py` | **dirty** | Role contract definitions | dirty (M) | high: not safe H8 base | review separately before H8 |
| `nexus/services/local_heal/phases/patch_synthesis.py` | **dirty** | Patch synthesis phase | dirty (M) | high: not safe H8 base | review separately before H8 |
| `tests/unit/local_heal/test_role_contract.py` | **dirty** | Role contract tests | dirty (M) | medium: test only | review separately before H8 |
| `tests/unit/local_heal/test_native_route_adapter.py` | **untracked** | Native route adapter tests | untracked (??) | medium: test only | review separately before H8 |
| `nexus/engine/capability_planner.py` | committed | RouteDecision truth source | committed | low: clean base | H8-1 seam target |
| `nexus/engine/capability_contracts.py` | committed | Receipt/plan contracts | committed | low: clean base | H8-1 seam target |
| `nexus/engine/capability_receipts.py` | committed | Receipt generation | committed | low: clean base | H8-1 seam target |
| `nexus/engine/autonomic_router.py` | committed | AutonomicRouter isolation | committed | low: clean base | H8-1 seam target |
| `nexus/engine/learning_policy_loader.py` | committed | Learning policy loader | committed | low: clean base | H8-1 seam target |

---

## 4. Safe Adapter Boundary

* Local model adapter must be behind **deny-by-default** resource policy.
* **No local model load by default.**
* **No model call by default.**
* **No network by default.**
* **No provider call by default.**
* Adapter output **cannot become route truth source**.
* CapabilityPlanner / RouteDecision remain route truth candidates.
* Receipts must record whether local model was allowed, loaded, called, and denied.
* **H8-1 should be test-only.**

---

## 5. Minimum Dry-run Contract

Fields needed for future controlled dry-run (do not implement in H8-0):

| Field | Type | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `local_model_provider` | str | `"ollama"` | Which local model provider |
| `local_model_name` | str | `"qwen3b"` | Which model to load |
| `local_model_allowed` | bool | `false` | Whether adapter is allowed to load model |
| `local_model_loaded` | bool | `false` | Whether model was actually loaded |
| `local_model_called` | bool | `false` | Whether model was actually called |
| `local_model_denied_reason` | str | `""` | Why model was denied (if applicable) |
| `network_allowed` | bool | `false` | Whether network access is allowed |
| `provider_call_allowed` | bool | `false` | Whether provider call is allowed |
| `model_load_allowed` | bool | `false` | Whether model load is allowed |
| `model_call_allowed` | bool | `false` | Whether model call is allowed |
| `route_truth_source` | str | `"capability_planner"` | Who owns route truth |
| `candidate_id` | str | `""` | Candidate identifier |
| `selected_candidate_hash` | str | `""` | Hash of selected candidate |
| `receipt_id` | str | `""` | Receipt identifier |
| `evidence_refs` | tuple | `()` | Evidence references |
| `verifier_result` | str | `""` | Verifier outcome |
| `public_claim_allowed` | bool | `false` | Whether public claim is allowed |

---

## 6. Dirty Workspace Risk

* Current checkout still has dirty local_heal files (5 production + 2 test).
* Current checkout still has dirty runtime artifacts (45 tracked + 37 untracked).
* Current checkout still has dirty pycache (30 tracked modified .pyc).
* Current checkout still has dirty CI/config candidates (.github/workflows, pyproject.toml, uv.lock).
* **H8 implementation must not start from dirty current checkout.**
* **H8 implementation should start from clean worktree after approval.**
* Dirty local_heal files may contain useful candidate work but must be reviewed separately.

---

## 7. Recommended H8-1

### H8-1 Controlled Local Model Adapter Deny-by-Default Tests

H8-1 should be **test-only** and should assert:

* `local_model_allowed=false` by default
* `local_model_loaded=false`
* `local_model_called=false`
* `provider_call_allowed=false`
* `network_allowed=false`
* `model_call_allowed=false`
* `model_load_allowed=false`
* adapter output cannot override RouteDecision
* receipt records denial reason
* no runtime model execution occurs

---

## 8. What Is Still Not Ready

| Item | Status |
| :--- | :--- |
| H8 runtime | not started |
| Local model adapter | not enabled |
| Qwen/Ollama | not called |
| Gemini/GPT provider | not called |
| Reconstructable Runtime | not ready |
| ACRouter | not enabled |
| Recovery/resume runtime | not ready |
| Production readiness | false |
| Public claim allowed | false |

---

## 9. Acceleration Decision

* **H7 cleanup execution is deferred.** Workspace stays dirty.
* **H8 proceeds through clean worktree strategy.** No cleanup needed before H8-1.
* **Next work should move to H8-1 tests** instead of more cleanup reports.
* Cleanup can be revisited after H8-1/H8-2 if needed.

---

## 10. Acceptance Criteria

* [x] Report exists: `docs/reports/h8_0_controlled_local_model_adapter_reality_map_v0.md`
* [x] No production code modified
* [x] No tests modified
* [x] No CI modified
* [x] No local model run
* [x] No provider/model/network/model-load/model-call executed
* [x] No runtime enabled
* [x] Adapter touchpoints mapped (13 files identified)
* [x] Deny-by-default boundary documented
* [x] H8-1 test-only task recommended
* [x] Final state: `H8_0_CONTROLLED_LOCAL_MODEL_ADAPTER_REALITY_MAP_DRAFT_READY_FOR_REVIEW`

---

## 11. Final State

`H8_0_CONTROLLED_LOCAL_MODEL_ADAPTER_REALITY_MAP_DRAFT_READY_FOR_REVIEW`

### Forbidden Final States

* `H8_RUNTIME_STARTED`
* `LOCAL_MODEL_ENABLED`
* `OLLAMA_CALLED`
* `QWEN_CALLED`
* `PROVIDER_CALLED`
* `MODEL_CALLED`
* `MODEL_LOADED`
* `ROUTING_READY`
* `PRODUCTION_READY`
* `PUBLIC_CLAIM_ALLOWED`

---

## 12. Verification Commands

```bash
# Report exists
test -f docs/reports/h8_0_controlled_local_model_adapter_reality_map_v0.md && echo H8_0_REPORT_EXISTS

# Safety boundary strings
grep -nE "H8_0_CONTROLLED_LOCAL_MODEL_ADAPTER_REALITY_MAP_DRAFT_READY_FOR_REVIEW|report_only=true|read_only=true|no local model run|no Ollama call|no Qwen call|no provider call|no model call|no network call|no model load|no model execution|no H8 runtime|no runtime routing enabled|local_model_ready=false|provider_ready=false|model_ready=false|routing_ready=false|production_ready=false|public_claim_allowed=false" docs/reports/h8_0_controlled_local_model_adapter_reality_map_v0.md

# Content references
grep -nE "native_route_adapter|backend_resource_policy|CapabilityPlanner|RouteDecision|AutonomicRouter|local_model_allowed|local_model_loaded|local_model_called|local_model_denied_reason|H8-1 Controlled Local Model Adapter Deny-by-Default Tests|H7 cleanup execution is deferred|clean worktree" docs/reports/h8_0_controlled_local_model_adapter_reality_map_v0.md

# Git state
git status --short
git diff --cached --name-only
git diff --name-only HEAD
```
