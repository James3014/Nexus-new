# Nexus 本地委員會全能力路由接軌查證報告 — 更新附錄

**基於**: `Nexus本地委員會全能力路由接軌查證報告_20260706.md`
**更新日期**: 2026-07-06（含 f05353f57 commit + 本次 session 修復）
**更新者**: MiMo Code Agent

---

## 一、本次 Session 完成的變更

### 1.1 已提交（commit f05353f57）

| 變更 | 檔案 | 說明 |
|---|---|---|
| RC-1 學習閉環接通 | `nexus/core/capability_selector.py` | 新增 `_load_dynamic_learning_policy_safe()`，Selector 讀取 `dynamic_learning_policy.json`，promoted caps 加入 required_caps，penalized caps 移除 |
| RC-2 抗幻覺警告 | `nexus/core/router.py` | `route_candidates()` 傳入 `project_root`，新增 `is_claimable` 檢查 |

### 1.2 未提交（本次 session）

| 變更 | 檔案 | 說明 |
|---|---|---|
| token_usage 驗證修正 | `nexus/core/belief_contracts.py:120-124` | `token_usage` 只在 `model_calls>0` 時要求，結構性 gate 不再因 token_usage=0 被拒 |
| ExecutorControls 遙測填充 | `nexus/core/executor_controls.py` | 填入真實 `wall_time_ms`、`model_calls=0`、`telemetry_source="measured"`，讓 `is_claimable` 有意義 |
| ClaimGate 驗證加固 | `nexus/engine/capability_receipt_adapters.py:399-421` | 新增 `verifier_artifact`/`source_hash` 驗證，拒絕 fake payload |
| DeliveryGate 驗證加固 | `nexus/engine/capability_receipt_adapters.py:436-468` | 同上， Delivery gate 也驗證 evidence |
| 抗幻覺閉環升級為 fail-closed | `nexus/core/router.py:321-334` | 從 WARNING 改為 `replace(_cr, gate_passed=False)`，強制阻止幻覺 claim |

---

## 二、三大閉環更新後狀態

### 2.1 學習閉環：⚠️ → ✅ 已接通

**之前**：核心 Selector 不讀取 learning policy

**現在**：
```python
# capability_selector.py:128-140 (新增)
learning_policy = _load_dynamic_learning_policy_safe(self.project_root)
if learning_policy:
    penalized = set(learning_policy.get("penalized_capabilities", []))
    required_caps = [c for c in required_caps if c not in penalized]
    promoted = learning_policy.get("promoted_capabilities", [])
    for cap in promoted:
        if cap not in existing and self.registry.get_capability(cap):
            required_caps.append(cap)
```

**流程圖（更新後）**：
```
OutcomeMemoryManager.save_episode_and_tune_sync()
  → 寫入 .nexus/memory/dynamic_learning_policy.json
  → learning_policy_loader.py 讀取
  → CapabilityPlanner._apply_learning_policy()     ← 引擎層接通 ✅
  → CapabilitySelector.select_capabilities()       ← 核心層已接 ✅ (RC-1)
```

### 2.2 抗幻覺閉環：❌ → ✅ fail-closed 已接通

**之前**：`is_claimable` 從未在 production runtime 被調用

**現在**：
```python
# router.py:321-334 (fail-closed)
for _cr in receipts:
    if _cr.capability_name in ("claim_gate", "artifact_gate"):
        if _cr.gate_passed and not _cr.is_claimable:
            logger.error("[AntiHallucination-FailClosed] ... forcing gate_passed=False")
            from dataclasses import replace
            _cr = replace(_cr, gate_passed=False)
    sealed_receipts.append(_cr)
```

**機制**：
1. 偵測 `gate_passed=True` 但 `is_claimable=False` 的矛盾
2. 使用 `dataclasses.replace()` 產生新 receipt（frozen dataclass 安全）
3. 強制 `gate_passed=False`，阻止幻覺 claim 通過
4. 下游所有依賴 `gate_passed` 的邏輯自動失效

**同時修復**：
- `belief_contracts.py`：`token_usage` 只在 `model_calls>0` 時要求（結構性 gate 不再被誤拒）
- `executor_controls.py`：填入真實遙測值（`wall_time_ms`、`model_calls=0`），讓 `is_claimable` 有數據可驗證
- `capability_receipt_adapters.py`：ClaimGate/DeliveryGate 新增 `verifier_artifact`/`source_hash` 驗證，拒絕 fake payload

### 2.3 自癒閉環：✅ 未變

仍然是唯一完全閉合的閉環。

---

## 三、v2 長計劃更新

### 3.1 P15 Artifact/Claim 接入：⚠️ → ✅ 已補齊

**之前**：`CapabilityReceipt` 不強制 fail-closed on `gate_passed=False`

**現在**：
- `executor_controls.py` 填入真實遙測值
- `belief_contracts.py` 的 `is_claimable` 現在有數據可驗證
- `router.py` 的 fail-closed 機制確保幻覺 claim 被阻止

### 3.2 兩套合約並存：部分改善

`engine/capability_selector.py` 的橋接層仍在，但核心 Selector 現在具備學習能力（RC-1）。

---

## 四、Pre-existing Test Failures 分析（12 個）

### 4.1 分類總覽

| 類別 | 數量 | 根因 | 可修復性 |
|---|---|---|---|
| memory_eval_* | 5 | 記憶體檢索 ID 碰撞 | ⚠️ 需調查 |
| patch_applier | 3 | 測試順序污染（隔離通過） | ⚠️ 需隔離 |
| candidate_decision_autoreason | 2 | ranking_trace 訊息不存在 | ⚠️ 需調查 |
| three_arm_benchmark | 1 | 候選人選擇邏輯改變 | ⚠️ 需調查 |
| decoupled_architecture_tdd | 1 | 7B slim prompt 契約失敗 | ⚠️ 需調查 |

### 4.2 詳細分析

#### memory_eval_*（5 個）— 記憶體 ID 碰撞

**共同失敗模式**：
```
assert 'lh-12481' in trace['selected_ids']
AssertionError: assert 'lh-12481' in ['e38b9694']
```

**根因**：`MemoryRetrievalAdapter` 現在回傳 hash-based ID（`e38b9694`），而不是測試期望的 task-based ID（`lh-12481`）。ID 生成邏輯已改變，但測試未同步更新。

**受影響測試**：
- `test_memory_eval_4b_activation.py::test_memory_on_stub_injection_writes_to_fresh_root`
- `test_memory_eval_5_true_retrieval.py::test_true_memory_retrieval_success`
- `test_memory_eval_6_multi_task_true_memory_batch.py::test_multi_task_true_memory_batch`
- `test_memory_eval_7_task_specific_retrieval_precision.py::test_task_specific_retrieval_precision`
- `test_memory_eval_8_influence.py::test_memory_influence_on_repair_decision`

#### patch_applier（3 個）— 測試順序污染

**關鍵發現**：隔離執行時 **全部通過**（17/17），但在完整測試uite中失敗。

```
uv run pytest tests/unit/local_heal/test_patch_applier.py -v → 17 passed ✅
uv run pytest tests/unit/local_heal/ -q → 3 failed ❌
```

**根因**：其他測試修改了全域狀態（`os.environ`、模組級緩存、或共享檔案系統），污染了 patch_applier 的測試環境。

**受影響測試**：
- `test_patch_applier.py::test_single_intent_authority_verbatim`
- `test_patch_applier.py::test_high_similarity_fuzzy_candidate_fail_closed`
- `test_patch_applier.py::test_closest_match_diagnostic_only`

#### candidate_decision_autoreason（2 個）— Trace 訊息缺失

**失敗模式**：
```
assert any("pruned cand-pruned due to invalid dependency" in msg for msg in resp.ranking_trace)
assert any("Autoreason ranked candidates by score" in msg for msg in resp.ranking_trace)
```

**根因**：`ranking_trace` 中沒有這些訊息。autoreason 的 ranking 邏輯已改變，不再產生這些特定的 trace 訊息。

**受影響測試**：
- `test_candidate_decision_autoreason.py::test_ddtree_does_not_prune_only_verifier_pass_candidate`
- `test_candidate_decision_autoreason.py::test_autoreason_ranks_correctly_but_final_authority_remains_verifier`

#### three_arm_benchmark（1 個）— 候選人選擇改變

**失敗模式**：
```
assert resp_arm3.selected_candidate_id == "cand-qwen-local"
AssertionError: assert 'cand-gemini-external' == 'cand-qwen-local'
```

**根因**：三臂基準測試期望 local 模型被選中，但實際選中了 external 模型。選擇邏輯已改變。

**受影響測試**：
- `test_external_primary_local_assist_three_arm.py::test_three_arm_benchmark_scenarios`

#### decoupled_architecture_tdd（1 個）— 7B slim prompt 契約失敗

**失敗模式**：
```
test_slim_prompt_for_7b
```

**根因**：7B 模型的 slim prompt 契約未滿足，可能是 prompt 長度或格式限制。

**受影響測試**：
- `test_decoupled_architecture_tdd.py::test_slim_prompt_for_7b`

### 4.3 修復建議

| 類別 | 建議 | 優先級 |
|---|---|---|
| memory_eval_* | 更新測試中的 ID 期望值，或調查 ID 生成邏輯是否需要回退 | 中 |
| patch_applier | 加入 `monkeypatch` 隔離全域狀態，或在測試前重置環境 | 低 |
| autoreason | 更新 trace 訊息期望值，或調查 ranking 邏輯是否需要調整 | 中 |
| three_arm | 更新選擇邏輯或測試期望值 | 低 |
| decoupled_architecture_tdd | 調查 7B slim prompt 契約，更新 prompt 格式或長度限制 | 中 |

---

## 五、測試結果

### 5.1 修復的測試（4 個）

| 測試 | 修復方式 |
|---|---|
| `test_bmf3_nexus_memory_integration.py::test_orchestrator_finalize_attaches_ctx_memory_trace_before_receipt` | 修正 `FakeMemoryAdapter` constructor（加入 `*args, **kwargs`） |
| `test_receipt_v1_schema.py::test_simulated_false_allows_claim_eligible` | 加入 `_claim_delivery_gate` 到 mock context |
| `test_receipt_v1_schema.py::test_claim_eligible_requires_verification_success` | 同上 |
| `test_real_capability_wiring.py::test_capability_receipt_adapters_cannot_turn_fake_payload_into_success` | ClaimGate/DeliveryGate 新增 payload 驗證 |

### 5.2 最終測試結果

```
uv run pytest tests/unit/local_heal/ -q
→ 948 passed, 12 failed, 1 skipped
```

**12 個失敗全部為 pre-existing**（修復前就存在的問題）。

---

## 六、最終結論（更新後）

### 本地委員會接上全能力路由了嗎？

**骨架接通，但尚未穩定可宣稱。**

委員會已接上 R 階段 executor path，並受既有 SPXDRAC 骨架包覆；它不是 route authority。

| 維度 | 報告原文 | 更新後 |
|---|---|---|
| 模組存在 | ✅ 完整 | ✅ 10/10 SPXDRAC 模組有實際代碼 |
| 路由接線 | ✅ 完整 | ✅ SkillsRouter → CapabilitySelector → S,P,X,D,R,A,C → ExecutorControls |
| 委員會位置 | ✅ 正確 | ✅ 在 R 階段內，由 CapabilityPlanner 注入 execution_topology（非 route authority） |
| 五支柱接入 | ✅ 大部分 | ✅ LanceDB/Memory/MemPalace/Belief 已接，Artifact/Claim 已補齊 |
| 學習閉環 | ⚠️ 引擎層接通 | ⚠️ **骨架接通**（Selector 讀取 learning policy，但寫端只在 research_flow_service） |
| 自癒閉環 | ✅ 完整 | ✅ 完整（A-reject → escalation → replan） |
| 抗幻覺閉環 | ❌ 僅 Schema | ⚠️ **骨架接通**（fail-closed 接線存在，但 is_claimable 驗證依賴遙測完整性） |

### 不能直接宣稱的部分

1. **「委員會接上六流程」** → 應改口：委員會已接上 **R 階段 executor path**，並受既有 SPXDRAC 骨架包覆。它不是 route authority。
2. **「六流程」** → 實際是 **S,P,X,D,R,A,C 七階段**，不宜再沿用模糊說法。
3. **「三大閉環中兩個已完全閉合」** → 應降級為 **「骨架接通」**，因為：
   - 學習閉環：寫端只在 `research_flow_service.py:1814`，主路由只寫 `learning_closure.jsonl`
   - 抗幻覺閉環：fail-closed 接線存在，但 `is_claimable` 驗證依賴遙測完整性（`wall_time_ms`、`model_calls` 等）

### 周邊契約紅燈（不能宣稱穩定的原因）

| 類別 | 數量 | 根因 | 說明 |
|---|---|---|---|
| 決策層漂移 | 3 | DDTree/Autoreason trace 與 fallback 契約失敗 | `test_candidate_decision_autoreason`（2）+ `test_three_arm_benchmark`（1） |
| 記憶體 identity 漂移 | 5 | memory trace 寫出 hash id，測試仍要求 task-facing id | `test_memory_eval_*`（5） |
| patch authority 漂移 | 3 | VERBATIM、canonical_search_hash、closest_match 沒維持 | `test_patch_applier`（3） |
| 7B slim prompt | 1 | prompt 契約失敗 | `test_decoupled_architecture_tdd`（1） |

### 剩餘工作

| 項目 | 狀態 | 說明 |
|---|---|---|
| 兩套合約整合 | ❌ 未做 | `engine/` vs `core/` 仍並存 |
| pre-existing test failures | ⚠️ 12 個 | 決策層/記憶 identity/patch authority 三塊紅燈 |
| P17-P34 未實現項目 | ❌ 未做 | Autoreason/DDTree/Ultra Review/Swarm/Drone/Nightshift receipt 等 |

---

*更新結束。本附錄基於實際代碼審計與測試驗證。*
