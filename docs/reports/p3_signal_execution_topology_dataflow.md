# P3 Signal → Execution Topology Data Flow Audit

## 1. signal_snapshot schema registry

### Base fields (from `route_signal_adapter.py:41-59`)

| Field | Type | Default | Set By | Optional |
|-------|------|---------|--------|----------|
| `routing_tier` | `str` | `""` | router | Yes |
| `routing_tier_reason` | `str` | `""` | router | Yes |
| `policy_loaded_count` | `int` | `0` | router | Yes |
| `policy_pruned_count` | `int` | `0` | router | Yes |

### Planner-enriched fields (`capability_planner.py:832-924`)

| Field | Type | Default | Set By | Optional |
|-------|------|---------|--------|----------|
| `execution_topology` | `str` | `"single_local_model"` | planner (env var) | No |
| `executor_provider` | `str` | `""` | planner (env var) | Yes |
| `executor_model` | `str` | `""` | planner (env var) | Yes |
| `local_executor_authority` | `str` | `""` | planner | Yes |
| `committee_profile` | `str` | `""` | planner | Yes |
| `local_committee_enabled` | `bool` | `False` | planner | Yes |
| `proposer_specs` | `list` | `[]` | planner | Yes |
| `judge_model` | `str` | `""` | planner | Yes |
| `diagnosis_committee_enabled` | `bool` | `False` | planner | Yes |
| `audit_committee_enabled` | `bool` | `False` | planner | Yes |
| `diagnosis_models` | `list` | `[]` | planner | Yes |
| `audit_models` | `list` | `[]` | planner | Yes |
| `delegated_retry_candidate_models` | `list` | `[]` | planner | Yes |
| `selected_executor` | `str` | `""` | planner | Yes |
| `ssd_route_map` | `dict` | `{}` | planner | Yes |
| `context_slimming_policy` | `dict` | `{}` | planner | Yes |
| `harness_relevance_policy` | `dict` | `{}` | planner | Yes |

### Consumer-required fields (NOT set by planner)

| Field | Type | Required By | Default if Missing |
|-------|------|-------------|-------------------|
| `protocol_mode` | `str` | executor (`ValueError`) | **CRITICAL: crashes** |
| `model_call_allowed` | `bool` | executor (`ValueError`) | **CRITICAL: crashes** |
| `candidate_enabled` | `bool` | adapter (`.get()`) | `False` (safe) |
| `advisory_enabled` | `bool` | adapter (`.get()`) | `False` (safe) |
| `isolated_solve_enabled` | `bool` | adapter (`.get()`) | `False` (safe) |
| `mutation_allowed` | `bool` | adapter + executor (`.get()`) | `False` (safe) |
| `verifier_allowed` | `bool` | adapter + executor (`.get()`) | `False` (safe) |
| `provider_timeout_sec` | `float` | executor (`.get()`) | `120.0` (safe) |

---

## 2. producer → consumer mapping table

| 欄位 | Producer 模組 | Consumer 模組 | 有無斷點 | 風險 |
|------|---------------|---------------|----------|------|
| `execution_topology` | `capability_planner.py:884` | executor:76, adapter | ✅ Complete | Low |
| `protocol_mode` | ❌ Not set by planner | executor:80 (ValueError) | 🔴 **斷點** | **High — crashes** |
| `model_call_allowed` | ❌ Not set by planner | executor:425 (ValueError) | 🔴 **斷點** | **High — crashes** |
| `executor_provider` | `capability_planner.py:879` | executor:436 | ✅ Complete | Low |
| `executor_model` | `capability_planner.py:880` | executor:437 | ✅ Complete | Low |
| `candidate_enabled` | ❌ Not set by planner | adapter:121 (`.get()`) | ⚠️ Always False | Medium |
| `advisory_enabled` | ❌ Not set by planner | adapter:183 (`.get()`) | ⚠️ Always False | Medium |
| `isolated_solve_enabled` | ❌ Not set by planner | adapter:186 (`.get()`) | ⚠️ Always False | Medium |
| `mutation_allowed` | ❌ Not set by planner | adapter:254, executor | ⚠️ Always False | Medium |
| `verifier_allowed` | ❌ Not set by planner | adapter:255, executor | ⚠️ Always False | Medium |
| `provider_timeout_sec` | ❌ Not set by planner | executor:884 (`.get()`) | ⚠️ Always 120.0 | Low |
| `committee_profile` | `capability_planner.py:887` | executor:907 | ✅ Complete | Low |
| `diagnosis_models` | `capability_planner.py:905` | executor (committee) | ✅ Complete | Low |
| `audit_models` | `capability_planner.py:910` | executor (committee) | ✅ Complete | Low |

---

## 3. execution_topology 回流路徑

```
CapabilityPlanner (capability_planner.py:884)
  └─ signal_snapshot["execution_topology"] = topology
       └─ RouteDecision.signal_snapshot (route_decision_adapter.py:86)
            └─ LocalModelExecutorRequest.route_context (executor.py:41)
                 └─ _resolve_execution_topology() (executor.py:64)
                      └─ raw_model_metadata["execution_topology"] (executor.py:1266,1581,2574)
                           └─ armor_receipt_gate validates (armor_receipt_gate.py:11)
                           └─ receipt.telemetries (receipt.py:504) — embedded, not top-level
```

**Note**: `execution_topology` is NOT a top-level key in `build_repair_receipt()`. It lives inside `raw_model_metadata` and is validated by the armor receipt gate.

---

## 4. route_context 關鍵路徑傳遞檢查

### CapabilityPlanner → adapter → executor

```
CapabilityPlanner.plan()
  └─ CapabilityPlan.signal_snapshot (line 939)
       └─ route_decision_adapter.py:86 — copied to RouteDecision.signal_snapshot
       └─ route_decision_adapter.py:122 — executor_controls built from plan
            └─ capability_ab_runner.py:14086 — finalized dict = route_context
                 └─ LocalModelExecutorRequest.route_context (executor.py:41)
```

### Committee path vs pipeline path 差異

| 特性 | Committee path | Pipeline path |
|------|----------------|---------------|
| Topology | `local_committee_only` | `localheal_pipeline` |
| Provider | `LocalCommitteeCandidateProvider` | `LocalHealPipelineCapabilityExecutor` |
| hash_match flow | raw_meta → route_context (P2-F) | raw_meta → route_context (P2-F) |
| protocol_mode | Hardcoded `"anchored_edit"` (line 1287) | Hardcoded `"anchored_edit"` (line 1584) |
| Committee diagnosis | Yes (lines 939-950) | No |
| Committee audit | Yes (lines 1061-1069) | No |

---

## 5. P2 修復後殘留斷點歸因

### 斷點 1: `protocol_mode` — 🔴 CRITICAL

- **位置**: `local_model_executor.py:80-81`
- **影響**: `_resolve_execution_topology()` raises `ValueError("Missing protocol_mode in signal_snapshot")`
- **根因**: Planner never injects `protocol_mode`. Orchestrator sets `os.environ["NEXUS_PROTOCOL_MODE"]` but not `signal_snapshot["protocol_mode"]`.
- **修復建議**: Planner should set `signal_snapshot["protocol_mode"] = os.environ.get("NEXUS_PROTOCOL_MODE", "anchored_edit")`

### 斷點 2: `model_call_allowed` — 🔴 CRITICAL

- **位置**: `local_model_executor.py:425-427`
- **影響**: `build_local_model_provider_from_signal_snapshot()` raises `ValueError("Missing model_call_allowed in signal_snapshot")`
- **根因**: Planner never injects `model_call_allowed`.
- **修復建議**: Planner should set `signal_snapshot["model_call_allowed"] = os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "0") == "1"`

### 斷點 3: `candidate_enabled` — ⚠️ MEDIUM

- **位置**: `capability_adapter.py:121`
- **影響**: Always defaults to `False`, candidate path never triggered via adapter
- **根因**: Planner never injects `candidate_enabled`
- **修復建議**: Planner should set `signal_snapshot["candidate_enabled"] = True` when executor is selected

### 斷點 4: `mutation_allowed` / `verifier_allowed` — ⚠️ MEDIUM

- **位置**: `capability_adapter.py:254-255`
- **影響**: Always defaults to `False`, mutation and verification never enabled
- **根因**: Planner never injects these fields
- **修復建議**: Planner should set these based on topology and policy

---

## 6. rank_bm25 dependency 判断

### 使用位置

| 檔案 | 行號 | 用途 |
|------|------|------|
| `nexus/services/local_heal/repomap.py` | 14 | File-level candidate ranking |
| `nexus/services/local_heal/granular_localizer.py` | 6 | Method-level ranking |
| `scratch/debug_localizer.py` | 3 | Debug script |

### 建議

1. **不應改成 optional import + fallback** — rank_bm25 是核心 localizer 的必要依賴，fallback 會降低定位品質
2. **應在 test 層 mock** — 測試不應依賴 rank_bm25 的實際計算結果
3. **已有的做法是正確的** — 當前 codebase 在 tests 中不直接測試 BM25 計算，而是通過 integration test 間接驗證

---

## 7. P3 實作前 unblock checklist

| 項目 | 優先級 | 說明 |
|------|--------|------|
| Planner inject `protocol_mode` | 🔴 P0 | 缺少此欄位 executor 會 crash |
| Planner inject `model_call_allowed` | 🔴 P0 | 缺少此欄位 executor 會 crash |
| Planner inject `candidate_enabled` | ⚠️ P1 | adapter 路徑永遠不會觸發 candidate |
| Planner inject `mutation_allowed` | ⚠️ P1 | adapter 路徑永遠不會允許 mutation |
| Planner inject `verifier_allowed` | ⚠️ P1 | adapter 路徑永遠不會允許 verification |
| `execution_topology` receipt visibility | ℹ️ P2 | 當前只在 raw_model_metadata 裡，不在 receipt 頂層 |
