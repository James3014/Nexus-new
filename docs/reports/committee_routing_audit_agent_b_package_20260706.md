# 本地委員會路由審計 — Agent B 可執行封包

**審計日期**: 2026-07-06
**審計基底**: `nexus_local_committee_routing_audit_update_20260706.md`
**實跑驗證**: `uv run pytest tests/unit/local_heal/ -q` → `948 passed, 12 failed, 1 skipped`

---

## 一、報告降級修正

### 1.1 數字修正

報告 §5.2 寫 `927 passed, 11 failed, 1 skipped`，實跑結果為 `948 passed, 12 failed, 1 skipped`。差距：+21 passed, +1 failed。

### 1.2 結論降級

報告 §6 寫「**是的，且三大閉環中兩個已完全閉合**」。降級為：

> 委員會已接上 `R` 階段 executor path，並受既有 SPXDRAC 骨架包覆。學習閉環與抗幻覺閉環的**骨架接線已存在**（code 中有 wiring），但**不能宣稱已穩定閉合**，因為：
> - 12 個 test failure 包含 decision contract (3)、memory trace (5)、patch authority (3)、7B prompt (1)
> - 其中 patch_applier 3 個 failure 是測試隔離污染（隔離跑全過），但 decision/memory/prompt 是真紅

### 1.3 術語修正

報告混用「六流程」與 `S,P,X,D,R,A,C`（7 個 phase）。應統一為「七階段」或明確列出 phase 名稱。

---

## 二、12 個 Failure 根因分類

### Category A: Decision Contract (3 failures)

| 測試 | 失敗根因 | 修復方向 |
|---|---|---|
| `test_candidate_decision_autoreason.py::test_ddtree_does_not_prune_only_verifier_pass_candidate` | trace message 不匹配：code 產出 `DDTree pruned {saved} candidates, kept {len}`，test 期望 `pruned cand-pruned due to invalid dependency` | 修 code trace message 或修 test expectation |
| `test_candidate_decision_autoreason.py::test_autoreason_ranks_correctly_but_final_authority_remains_verifier` | trace message 不匹配：code 產出 `Autoreason ranked by borda, winner={winner}`，test 期望 `Autoreason ranked candidates by score` | 同上 |
| `test_external_primary_local_assist_three_arm.py::test_three_arm_benchmark_scenarios` | DDTree 未觸發：test 設 `NEXUS_ENABLE_DDTREE=1` env var，但 adapter 只看 `selected_capabilities` 參數，不讀 env var | 修 adapter 讀 env var fallback，或修 test 傳入 `selected_capabilities=("ddtree",)` |

**核心問題**: `candidate_decision_adapter.py` 的 `select_candidate()` 方法在 DDTree/Autoreason 分支中只檢查 `selected_capabilities` 參數，但 `NEXUS_ENABLE_DDTREE` env var 沒被轉換為 `selected_capabilities`。test 設了 env var 但 adapter 不讀。

**修復選項**:
- Option 1 (推薦): 在 `select_candidate()` 開頭加 env var → capabilities 轉換邏輯
- Option 2: 改 test 直接傳 `selected_capabilities=("ddtree",)`

### Category B: Memory Trace Contract (5 failures)

| 測試 | 失敗根因 |
|---|---|
| `test_memory_eval_4b_activation.py` | `trace_status == "TRACE_MISSING"` 而非 `"TRACE_AVAILABLE"` — memory stub injection 未生效 |
| `test_memory_eval_5_true_retrieval.py` | 同上 |
| `test_memory_eval_6_multi_task_true_memory_batch.py` | 同上 |
| `test_memory_eval_7_task_specific_retrieval_precision.py` | 同上 |
| `test_memory_eval_8_influence.py` | 同上 + `primary_selected_id == ""` 而非 `"lh-12481"` |

**核心問題**: `HealOrchestrator.run()` 中的 memory arm stub injection 路徑沒有產生 `TRACE_AVAILABLE` 的 trace。所有 5 個 test 都在第一個 assert 就 fail 了（`trace_status`），所以報告說的 ID 碰撞是 secondary issue——primary issue 是 stub injection 根本沒跑。

**修復方向**: 檢查 `orchestrator.py` 中 `memory_arm == "nexus_memory_on"` 分支是否正確呼叫了 memory retrieval adapter 並產生 trace。

### Category C: Patch Authority (3 failures — 隔離污染)

| 測試 | 隔離跑 | 全量跑 |
|---|---|---|
| `test_single_intent_authority_verbatim` | ✅ pass | ❌ fail |
| `test_high_similarity_fuzzy_candidate_fail_closed` | ✅ pass | ❌ fail |
| `test_closest_match_diagnostic_only` | ✅ pass | ❌ fail |

**核心問題**: 這 3 個 test 隔離跑全過（17/17），全量跑 fail。根因是其他 test 污染了全域狀態（`os.environ`、模組級緩存、或共享檔案系統）。

**修復選項**:
- Option 1 (推薦): 在 fail 的 test 加 `monkeypatch` 隔離全域狀態
- Option 2: 加 `@pytest.mark隔离` 標記，讓這些 test 在獨立 subprocess 跑
- Option 3: 找到污染源並修復

### Category D: 7B Slim Prompt (1 failure)

| 測試 | 失敗根因 |
|---|---|
| `test_decoupled_architecture_tdd.py::test_slim_prompt_for_7b` | 7B prompt (1116 chars) 比 14B prompt (993 chars) 還長，違反 slim contract |

**核心問題**: `prompt_builder.py` 的 7B 分支（`is_small_local=True`）產出的 prompt 包含冗長的 "HARD OUTPUT CONTRACT" + "VALID EXAMPLE" + "FORBIDDEN" 列表，反而比 full prompt 更長。

**修復方向**: 精簡 7B prompt，移除冗餘說明，確保 `len(slim) < len(full)`。

---

## 三、Agent B 四個 Task 封包

### Task 1: `U3-Committee-Decision-Contract`

**Status boundary**: Decision-contract repair only. 不改 committee executor topology, 不改 route order, 不 claim committee solve capability.

**Goal**: Restore DDTree/Autoreason observable contract and local-assist fallback selection.

**Root cause**: `candidate_decision_adapter.py:47` 檢查 `if "ddtree" in selected_capabilities`，但 test 只設 env var `NEXUS_ENABLE_DDTREE=1` 而不傳 `selected_capabilities`。同時 trace message 格式不匹配。

**修復策略**:

1. 在 `candidate_decision_adapter.py` 開頭加入 env var → capabilities fallback:
```python
if not selected_capabilities:
    caps = []
    if os.environ.get("NEXUS_ENABLE_DDTREE") == "1":
        caps.append("ddtree")
    if os.environ.get("NEXUS_ENABLE_AUTOREASON") == "1":
        caps.append("autoreason")
    selected_capabilities = tuple(caps)
```

2. 統一 trace message 格式（code 或 test 選一邊改）:
   - DDTree: `f"DDTree pruned {saved} candidates, kept {len(active_candidates)}"` → 需要 test 也用這個格式，或 code 改成 test 期望的格式
   - Autoreason: `f"Autoreason ranked by borda, winner={winner}"` → 同上

**Allowed files**:
- `/Users/jameschen/Workspace/nexus/nexus/services/local_heal/candidate_decision_adapter.py`
- `/Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_candidate_decision_autoreason.py`
- `/Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_external_primary_local_assist_three_arm.py`

**Required commands**:
```bash
python3 -m py_compile nexus/services/local_heal/candidate_decision_adapter.py tests/unit/local_heal/test_candidate_decision_autoreason.py tests/unit/local_heal/test_external_primary_local_assist_three_arm.py
uv run pytest tests/unit/local_heal/test_candidate_decision_autoreason.py tests/unit/local_heal/test_external_primary_local_assist_three_arm.py -q
```

**Success criteria**: 3 tests pass (was 1 pass, 3 fail).

---

### Task 2: `U3-Memory-Identity-Trace-Contract`

**Status boundary**: Memory-trace contract repair only. 不 claim memory uplift, 不 tune retrieval ranking.

**Goal**: Make memory stub injection produce `TRACE_AVAILABLE` trace; expose stable external identity.

**Root cause**: `HealOrchestrator.run()` 的 memory arm stub injection 路徑沒有產生 `TRACE_AVAILABLE` trace。所有 5 個 test 都 fail 在 `trace_status == "TRACE_MISSING"`。ID mismatch 是 secondary（只有 trace 產生後才會 hit）。

**修復策略**:

1. 檢查 `orchestrator.py` 中 `memory_arm == "nexus_memory_on"` 分支，確保 stub injection 正確呼叫 memory retrieval adapter 並回傳 `retrieved > 0` 的結果
2. 確認 `build_memory_trace_from_adapter()` 在 stub 模式下產生 `trace_status="TRACE_AVAILABLE"`
3. 如果 ID 也需要修，確保 `selected_ids` 和 `primary_selected_id` 使用穩定的 external contract

**Allowed files**:
- `/Users/jameschen/Workspace/nexus/nexus/services/local_heal/memory_retrieval_adapter.py`
- `/Users/jameschen/Workspace/nexus/nexus/services/local_heal/memory_trace.py`
- `/Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_memory_eval_4b_activation.py`
- `/Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_memory_eval_5_true_retrieval.py`
- `/Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_memory_eval_6_multi_task_true_memory_batch.py`
- `/Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_memory_eval_7_task_specific_retrieval_precision.py`
- `/Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_memory_eval_8_influence.py`

**Required commands**:
```bash
python3 -m py_compile nexus/services/local_heal/memory_retrieval_adapter.py nexus/services/local_heal/memory_trace.py
uv run pytest tests/unit/local_heal/test_memory_eval_4b_activation.py tests/unit/local_heal/test_memory_eval_5_true_retrieval.py tests/unit/local_heal/test_memory_eval_6_multi_task_true_memory_batch.py tests/unit/local_heal/test_memory_eval_7_task_specific_retrieval_precision.py tests/unit/local_heal/test_memory_eval_8_influence.py -q
```

**Success criteria**: 5 tests pass (was 0 pass, 5 fail).

---

### Task 3: `U3-Patch-Authority-Diagnostics-Contract`

**Status boundary**: Patch authority/diagnostic repair only. 不改 committee routing, 不改 verifier policy.

**Goal**: 3 patch_applier tests pass in full suite (they already pass in isolation).

**Root cause**: 全量跑時其他 test 污染了全域狀態。隔離跑 17/17 全過。

**修復策略**:

1. 找到污染源：用 `pytest -x` 在 full suite 中逐步排除，定位哪個 test 污染了 patch_applier 的環境
2. 加 `monkeypatch` 隔離：在 fail 的 3 個 test 中加 `monkeypatch.delenv()` 或 `monkeypatch.setattr()` 確保環境乾淨
3. 或加 `@pytest.mark.isolation` 標記讓這些 test 在獨立 subprocess 跑

**Allowed files**:
- `/Users/jameschen/Workspace/nexus/nexus/services/local_heal/patch_applier.py`
- `/Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_patch_applier.py`

**Required commands**:
```bash
python3 -m py_compile nexus/services/local_heal/patch_applier.py tests/unit/local_heal/test_patch_applier.py
uv run pytest tests/unit/local_heal/test_patch_applier.py -q
uv run pytest tests/unit/local_heal/ -q  # verify 3 tests pass in full suite too
```

**Success criteria**: 3 tests pass in full suite (they already pass in isolation).

---

### Task 4: `U3-7B-Slim-Prompt-Contract`

**Status boundary**: Prompt-size contract only. 不改 patch protocol semantics.

**Goal**: Restore the explicit 7B slim-prompt contract: `len(slim_7b) < len(full_14b)`.

**Root cause**: `prompt_builder.py:36-59` 的 7B 分支產出 1116 chars，但 full prompt (lines 61-77) 只有 993 chars。7B prompt 包含冗長的 "HARD OUTPUT CONTRACT" + "VALID EXAMPLE" + "FORBIDDEN" 列表。

**修復策略**:

精簡 7B prompt，移除冗餘說明：
- 移除 "VALID EXAMPLE (copy this format exactly):" 後的完整 example（已有 `few_shot`）
- 精簡 "FORBIDDEN" 列表為 2-3 行
- 確保 `len(slim) < len(full)`

**Allowed files**:
- `/Users/jameschen/Workspace/nexus/nexus/services/local_heal/prompt_builder.py`
- `/Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_decoupled_architecture_tdd.py`

**Required commands**:
```bash
python3 -m py_compile nexus/services/local_heal/prompt_builder.py tests/unit/local_heal/test_decoupled_architecture_tdd.py
uv run pytest tests/unit/local_heal/test_decoupled_architecture_tdd.py -k slim_prompt_for_7b -q
```

**Success criteria**: 1 test pass (was 0 pass, 1 fail).

---

## 四、Forbidden Claims (Agent B)

- ❌ Do not claim committee fully spans all seven phases
- ❌ Do not claim verified repair
- ❌ Do not claim production_ready
- ❌ Do not claim public_claim_allowed
- ❌ Do not rewrite the audit report conclusion to "fully connected" until `tests/unit/local_heal/ -q` is green or remaining red tests are explicitly reclassified with evidence
- ❌ Do not claim "三大閉環已完全閉合" — 可以說「骨架接線已存在」

## 五、完成後預期

修完 4 個 task 後，`uv run pytest tests/unit/local_heal/ -q` 預期：
- Category A (3): 從 fail → pass
- Category B (5): 從 fail → pass
- Category C (3): 從 fail → pass（如果找到隔離方案）
- Category D (1): 從 fail → pass

**最佳情況**: `948+12 passed, 0 failed, 1 skipped`
**保守估計**: `948+9 passed, 3 failed, 1 skipped`（如果隔離污染難修）
