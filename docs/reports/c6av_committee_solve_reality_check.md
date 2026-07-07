# C6AV: Committee Solve Reality Check

**Date**: 2026-07-07  
**Task**: C6AV-committee-solve-reality-check  
**Scope**: Verify whether current local committee + R/D/A + retry path wiring produces real solve uplift. No new capabilities. No refactor. No model ceiling claims.

---

## 1. 問題摘要

三個核心問題：
1. D/A committee 是不是真的有進主路徑？
2. 它有沒有改變 winner / verifier 結果 / solve 結果？
3. 現在 fail 的主因是 selection、diagnosis、audit、retry content，還是模型 semantic coverage？

---

## 2. 證據清單

### Phase 0 — Truth Audit (8 tests, all PASS, 0.23s, no models required)

| Test | Finding |
|---|---|
| `test_planner_does_not_inject_diagnosis_committee_enabled` | CapabilityPlanner **never injects** `diagnosis_committee_enabled` or `audit_committee_enabled` into `signal_snapshot` for `local_committee_only` topology |
| `test_diagnose_returns_none_when_gate_absent` | `diagnose_with_committee()` returns `None` when gate flag is absent |
| `test_audit_returns_none_when_gate_absent` | `audit_with_committee()` returns `None` when gate flag is absent |
| `test_r_phase_committee_active` | R-phase committee **IS active**: `proposer_specs` (2 distinct models) + `judge_model` are injected by planner |
| `test_run_calls_diagnose_and_audit` | `CommitteeOrchestrator.run()` source contains `diagnose_with_committee` (line 264) and `audit_with_committee` (line 552) calls |
| `test_parent_orchestrator_has_no_diagnose_or_audit` | `HealOrchestrator.run()` (parent) does **NOT** contain D/A committee calls |
| `test_da_committee_both_noop_with_planner_snapshot` | With planner's actual `signal_snapshot`, both D/A return `None` |

### Code Evidence

| File | Line | Evidence |
|---|---|---|
| `committee_orchestrator.py` | 264 | `self.diagnose_with_committee(ctx)` — called in `run()` before linear phases |
| `committee_orchestrator.py` | 552 | `self.audit_with_committee(ctx)` — called in `run()` after verify |
| `committee_orchestrator.py` | 103 | `if not signal_snapshot.get("diagnosis_committee_enabled", False): return None` — **gate never opens** |
| `committee_orchestrator.py` | 187 | `if not signal_snapshot.get("audit_committee_enabled", False): return None` — **gate never opens** |
| `capability_planner.py` | 886-897 | Injects `local_committee_enabled=True` + `proposer_specs` + `judge_model` for `local_committee_only` — but **NOT** `diagnosis_committee_enabled` / `audit_committee_enabled` |

### Truth Chain (production runtime)

```
diagnosis → [DEAD: gate=False, return None]
    ↓
plan/strategy → [ACTIVE: linear phases run]
    ↓
patch winner → [ACTIVE: R-phase committee, proposer collection + judge selection]
    ↓
audit/verifier → [verifier: ACTIVE] [audit: DEAD: gate=False, return None]
    ↓
solved → [depends on verifier_result + hash_match + candidate_isolated]
```

---

## 3. 4x Matrix 結果

| Combo | Topology | Models | Solved | Winner | Verifier | Semantic Retry | Delegated Retry | Duration | Failure Bucket |
|---|---|---|---|---|---|---|---|---|---|
| 1 (qwen alone) | localheal_pipeline | qwen only | ❌ | N/A | fail (blocked) | not reached | not_invoked | 0.07s | **retry_not_reached** |
| 2 (qwen+ornith) | local_committee_only | qwen+ornith+judge | ✅ | qwen (primary) | pass | not needed | not_invoked | 31.38s | N/A (solved) |
| 3 (qwen+deepseek) | local_committee_only | qwen+deepseek+judge | ✅ | qwen (primary) | pass | not needed | not_invoked | 23.02s | N/A (solved) |
| 4 (triple) | local_committee_only | qwen+deepseek+judge+ornith(delegated) | ✅ | qwen (primary) | pass | not needed | not_invoked | 24.9s | N/A (solved) |

### Committee Candidate Detail (combo 2-4)

| Combo | Judge Called | Primary Called | Secondary Called | Winner | Secondary Winner |
|---|---|---|---|---|---|
| 2 | ✅ qwen2.5-s2t-advisor:3b | ✅ qwen2.5-coder:7b | ✅ ornith:9b | qwen (primary) | ❌ |
| 3 | ✅ qwen2.5-s2t-advisor:3b | ✅ qwen2.5-coder:7b | ✅ deepseek-coder:6.7b | qwen (primary) | ❌ |
| 4 | ✅ qwen2.5-s2t-advisor:3b | ✅ qwen2.5-coder:7b | ✅ deepseek-coder:6.7b | qwen (primary) | ❌ |

### D/A Committee Activation

| Combo | D-phase committee | A-phase committee |
|---|---|---|
| 1 | N/A (localheal_pipeline, no CommitteeOrchestrator) | N/A |
| 2 | ❌ return None (gate flag absent) | ❌ return None (gate flag absent) |
| 3 | ❌ return None (gate flag absent) | ❌ return None (gate flag absent) |
| 4 | ❌ return None (gate flag absent) | ❌ return None (gate flag absent) |

---

## 4. Primary Root Cause per Combo

| Combo | Primary Root Cause | Rationale |
|---|---|---|
| 1 (qwen alone) | **retry_not_reached** | `localheal_pipeline` topology → HealOrchestrator path → `actual_provider_invoked: false`, `no_model_call_reason: model_not_called`, `failure_class: empty_response`. Pipeline never called Ollama. 0.07s duration = pipeline returned immediately without model invocation. This is a **pipeline path issue**, not a committee/selection/diagnosis/audit/retry-content issue. |
| 2 (qwen+ornith) | **N/A — solved first_pass** | R-phase committee active. qwen (primary) won, ornith (secondary) lost. Verifier pass. No retry needed. |
| 3 (qwen+deepseek) | **N/A — solved first_pass** | R-phase committee active. qwen (primary) won, deepseek (secondary) lost. Verifier pass. No retry needed. |
| 4 (triple) | **N/A — solved first_pass** | R-phase committee active. qwen (primary) won, deepseek (secondary) lost. Delegated retry candidates (qwen+deepseek+ornith) injected but **not triggered** (first pass solved). Verifier pass. |

---

## 5. 結論：下一步只選一個

### D/A committee 有沒有改變結果？

**無法判定 — D/A committee 從未執行。**

- `CommitteeOrchestrator.run()` 確實呼叫 `diagnose_with_committee()` (line 264) 和 `audit_with_committee()` (line 552)
- 但兩者的 gate flag（`diagnosis_committee_enabled` / `audit_committee_enabled`）**從未被 CapabilityPlanner 注入**
- 導致 `diagnose_with_committee()` 和 `audit_with_committee()` 在 production runtime 中**永遠 return None**
- D/A committee 是 **connected in code, disconnected at runtime**（dead code in production）

### qwen+deepseek 為什麼還 fail？

**它沒有 fail — solved。** Combo 3 在 23.02s 內 first pass 解決。

### triple 為什麼還 fail？

**它沒有 fail — solved。** Combo 4 在 24.9s 內 first pass 解決。Delegated retry candidate models（qwen+deepseek+ornith）被注入但未觸發。

### 現在最值得動的是什麼？

**不是 committee policy，不是 solve content，不是更強模型。**

- Combo 1 的唯一 failure 是 `localheal_pipeline` topology 的 pipeline 路徑問題（model_not_called）
- Combo 2-4 全部 solved — 但這是因為 toy-math task（x*2→x*3）太簡單，first pass 就解決了
- R-phase committee 運作正常但 **沒有機會展示價值**（winner 永遠是 qwen primary，secondary 從未贏）
- D/A committee **沒有機會展示價值**（gate flag 從未注入，從未執行）

### 決策樹判定

```
D/A committee trace exists but does not change any outcome
→ FALSE: trace does NOT exist (gate never opened, always return None)

If telemetry cannot prove whether D/A mattered
→ TRUE: D/A committee never executed, no trace generated
→ 結論 = observability gap (gate flag gap, not telemetry field gap)
→ 下一步 = inject gate flags to activate D/A committee, then re-run on harder task
```

**結論：D/A committee 在 code 中已接上（run() 呼叫它），但在 runtime 中從未執行（CapabilityPlanner 從未注入 gate flag）。R-phase committee 運作正常但在簡單 task 上無法展示 committee 的真實價值。当前唯一 failure（combo 1）是 pipeline 路徑問題，不是 committee 問題。**

---

## 6. Next Automatic Action

```
Next automatic action:
Inject `diagnosis_committee_enabled=True` + `audit_committee_enabled=True` + `diagnosis_models` + `audit_models` into CapabilityPlanner signal_snapshot for `local_committee_only` topology (capability_planner.py:886-897 block), then re-run 4x matrix on a task where first_pass fails (e.g. toy-math-forced-retry with local_committee_only topology) to measure whether D/A committee changes winner selection, verifier outcome, or solve result.
```

---

## Appendix: Files Touched

| File | Change |
|---|---|
| `tests/unit/local_heal/test_c6av_committee_solve_reality_check.py` | NEW — Phase 0 truth audit (8 tests) |
| `docs/reports/c6av_committee_solve_reality_check.md` | NEW — this report |

**Total files touched: 2** (within max 8 limit)  
**No production code modified.** No new capabilities. No refactor. No API changes.  
**Models used**: qwen2.5-coder:7b-instruct, ornith:9b, deepseek-coder:6.7b-instruct, qwen2.5-s2t-advisor:3b (all via Ollama, serial execution, RAM cleared between combos)  
**Test result**: 8 passed, 0 failed (Phase 0)  
**Live benchmark**: 4 combos serial, 3 solved / 1 failed (pipeline path issue)

