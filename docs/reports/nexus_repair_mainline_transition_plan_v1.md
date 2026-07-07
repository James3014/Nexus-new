# Nexus Repair Mainline Transition Plan v1

> 目標：把 Nexus 從「多模型實驗堆疊」整理成「模型提案、Nexus 理解、Nexus 驗證、Nexus 決策」的修復系統。
>
> 約束：預設走 `local_first_cascade`（ornith:9b → qwythos:9b → 14b/cloud）。Cloud 定位為硬題路由工具（Phase 5），非預設主線。所有 topology 共用同一套 CanonicalPatchCandidate + hash-chain 地基。
>
> 文件用途：後續 agent 的對齊文件，所有改動前先看這裡。

---

## Phase 0: 現狀盤點

### Dirty Tree 分類 (git diff --stat, 2026-07-08)

所有 `__pycache__` 檔案自動忽略，不列入分類。

#### 分類標籤

| 標籤 | 意義 | 處置 |
|------|------|------|
| `mainline_candidate` | 核心修復路徑，應進主線 | 整理後 commit |
| `committee_experiment` | Committee/D/A-committee 實驗 | 保持實驗狀態，不進主線 |
| `memory_eval_experiment` | Memory evaluation 實驗 | 保持實驗狀態，不進主線 |
| `benchmark_experiment` | Benchmark/ablation 腳本 | 保持實驗狀態，不進主線 |
| `artifact_only` | Runtime 產出、一次性報告、receipt 資料 | 不進主線，保留在 dirty tree |
| `needs_recheck` | 需要再確認才能歸類 | 審查後決定 |
| `ignore` | 自動生成檔案 | 永不理會 |

#### 分類明細

##### Core Repair Path (`mainline_candidate`)

| 檔案 | 行數 | 改動摘要 |
|------|:----:|---------|
| `nexus/core/executor_controls.py` | +14 | telemetry timing 修復，CapabilityReceipt 補真實量測 |
| `nexus/core/router.py` | +11 | AntiHallucination fail-closed: gate_passed=True 但 is_claimable=False → 強制 gate_passed=False |
| `nexus/core/belief_contracts.py` | +7 | Belief contracts |
| `nexus/core/parity_audit.py` | +8 | Parity audit |
| `nexus/engine/local_model_policy.py` | +3 | ModelProfile.get_api_type() — qwythos `/api/chat` routing |
| `nexus/engine/phases/audit.py` | +2 | Audit phase tweak |
| `nexus/services/local_heal/local_model_provider.py` | +43 | api_type routing：OllamaLocalModelProvider 支援 `/api/chat` messages |
| `nexus/services/local_heal/protocol.py` | +1 | Protocol 微調 |
| `nexus/services/local_heal/isolated_local_solve_loop.py` | +7 | Solve loop |
| `tests/unit/local_heal/test_receipt_v1_schema.py` | +1 | Receipt schema test |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | +20 | 治理規則來源（lesson writeback），非 runtime artifact |

##### 重疊檔案歸屬規則

以下檔案同時出現在多個分類。歸屬規則：
- `local_model_capability_wiring.py` (+12)：primary = `committee_experiment`（改動動機是 committee wiring），secondary = `memory_eval_experiment`（共用）。Split 時以 committee 線為主體，memory eval 修改部分（若可分離）另標。
- `local_model_executor.py` (+183)：見 `needs_recheck`，split 後依內容歸類。
- `isolated_workspace_apply.py` (+59)：見 `needs_recheck`，split 後依內容歸類。

##### Committee Experiment (`committee_experiment`)

| 檔案 | 行數 | 改動摘要 |
|------|:----:|---------|
| `nexus/engine/capability_planner.py` | +34 | committee config injection, D/A committee gates, delegated retry models |
| `nexus/services/local_heal/committee_orchestrator.py` | +57 | Committee orchestration + D/A diagnosis/audit |
| `nexus/services/local_heal/local_committee_candidate_provider.py` | +15 | Committee candidate provider |
| `nexus/services/local_heal/local_model_capability_executors.py` | +30 | Capability executors (committee path) |
| `nexus/services/local_heal/local_model_capability_wiring.py` | +12 | Capability wiring |
| `nexus/services/local_heal/local_model_executor.py` | +183 | 主要執行器：committee topology, D-phase diagnosis, A-phase audit, forensic apply mismatch, git pre-image fallback |
| `nexus/services/local_heal/prompt_builder.py` | +69 | C6AJ CapabilityPromptInjector retry prompt builder |
| `tests/unit/local_heal/test_delegated_retry_signal.py` | +88 | Delegated retry tests |

##### Memory Eval Experiment (`memory_eval_experiment`)

| 檔案 | 行數 | 改動摘要 |
|------|:----:|---------|
| `tests/unit/local_heal/test_memory_eval_4b_activation.py` | +24 | Memory eval |
| `tests/unit/local_heal/test_memory_eval_5_true_retrieval.py` | +24 | Memory eval |
| `tests/unit/local_heal/test_memory_eval_6_multi_task_true_memory_batch.py` | +25 | Memory eval |
| `tests/unit/local_heal/test_memory_eval_7_task_specific_retrieval_precision.py` | +26 | Memory eval |
| `tests/unit/local_heal/test_memory_eval_8_influence.py` | +26 | Memory eval |
| `tests/unit/local_heal/test_bmf3_nexus_memory_integration.py` | +2 | Memory integration |
| `nexus/services/local_heal/local_model_capability_wiring.py` | +12 | (shared with committee) |

##### Benchmark Experiment (`benchmark_experiment`)

| 檔案 | 行數 | 改動摘要 |
|------|:----:|---------|
| `scripts/bench/capability_ab_runner.py` | +5 | AB runner |
| `scripts/bench/m1_real_local_solve_benchmark.py` | +97 | M1 real local solve benchmark (committee mode) |
| `tests/benchmark/test_heterogeneous_local_model_armor.py` | +22 | Heterogeneous model armor |
| `tests/benchmark/test_m1_real_local_solve_benchmark.py` | +71 | NEW: M1 benchmark test |

##### Artifacts & Reports (`artifact_only`)

| 檔案 | 行數 | 說明 |
|------|:----:|------|
| `.nexus/reports/learn/learning_closure.jsonl` | +1553 | Learning closure telemetry |
| `artifacts/runtime/ao2_live_regression_entrypoints_v0/*.json` | ~14 | Regression結果 |
| `artifacts/runtime/av_executable_benchmark_substrate_v0/execution_results/*.json` | ~100 | Benchmark execution results |
| `artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs/C_1/nexus_memory_on/*.json` | ~21 | Memory eval results |
| `docs/reports/ac2_14b_resource_gated_fallback_eval_v0.md` | +115 | 14B resource evaluation report |

##### Meta / Other (`artifact_only`)

| 檔案 | 行數 | 說明 |
|------|:----:|------|
| `.serena/project.yml` | +73 | Editor/IDE config |
| `Daily_Log.md` | +38 | Daily log |

##### Needs Recheck (`needs_recheck`)

| 檔案 | 行數 | 原因 | Split 指引 |
|------|:----:|------|-----------|
| `nexus/services/local_heal/local_model_executor.py` | +183 | 混雜 core repair（git pre-image fallback, compute_failure_class fix, forensic_apply_mismatch）與 experiment（committee topology, D/A audit/diagnosis） | Core repair 部分 → mainline_candidate；committee/D/A 部分 → committee_experiment；無法分離的 glue 按最小影響保留 |
| `nexus/services/local_heal/isolated_workspace_apply.py` | +59 | 59 lines 改動需確認哪些是 core 哪些是 experiment | 同 `local_model_executor.py` 原則 |

> **Gate**: P1 開始前，`needs_recheck` 檔案必須完成 split 歸類。未 split 前假設為 experiment，不進 mainline。

---

## Phase 1: CanonicalPatchCandidate — 統一模型輸出契約

> **前置條件**: P0.5 `needs_recheck` split 已完成。`isolated_workspace_apply.py` 和 `local_model_executor.py` 的 core repair 部分已拆入 mainline_candidate，committee 部分已歸入 experiment。

### 設計

```python
@dataclass
class CanonicalPatchCandidate:
    """所有模型輸出先轉成同一種內部候選。"""
    # 來源
    source_format: str  # SEARCH_REPLACE | UNIFIED_DIFF | PARTIAL_DIFF | LINE_SPAN_EDIT | FUNCTION_REPLACEMENT | NATURAL_LANGUAGE_REPAIR_INTENT | EMPTY_OR_REFUSAL | MALFORMED_OUTPUT
    raw_output: str
    raw_output_hash: str  # sha256 of raw output
    
    # Normalization
    normalized_patch: str | None
    normalized_patch_hash: str | None
    normalization_steps: list[str]  # e.g. ["unwrapped_markdown_fence", "converted_to_ssrp"]
    
    # Anchoring
    target_file: str
    target_symbol: str
    line_span: tuple[int, int] | None
    old_block_hash: str | None  # sha256 of SEARCH block
    
    # Safety
    safety_flags: list[str]  # e.g. "prose_contamination", "empty_after_cleanup"
    parse_error_kind: str = ""  # empty = no error
    
    # Provenance
    model_name: str
    model_role: str  # primary | secondary | judge | cloud
    provider: str  # ollama | openai | gemini
    api_type: str  # chat | generate
```

```python
@dataclass
class OutputUnderstandingResult:
    """Nexus 對模型輸出的理解結果。"""
    candidate: CanonicalPatchCandidate | None
    understood: bool  # False → malformed/refusal
    failure_reason: str  # empty if understood
```

### 支援的來源格式

| 格式 | 來源模型 | 現有處理 |
|------|---------|---------|
| `SEARCH_REPLACE` | qwythos (/api/chat), qwen | `protocol.py` classify_format → `SOLID_SEARCH_REPLACE` |
| `UNIFIED_DIFF` | ornith (/api/chat) | `DiffToSSRPConverter` in `patch_synthesis.py:231` |
| `FENCED_SEARCH_REPLACE` | ornith (/api/generate) | `protocol.py` → `FENCED_SEARCH_REPLACE` → unwrap |
| `NATURAL_LANGUAGE_REPAIR_INTENT` | 弱模型 refusal | 尚無處理 |
| `EMPTY_OR_REFUSAL` | 任何模型 | `compute_failure_class` → `empty_response` |
| `MALFORMED_OUTPUT` | 語法錯誤 | `protocol_parse_failed` |

### 受影響檔案

- `nexus/services/local_heal/output_understanding.py` — **NEW**: canonical candidate factory
- `nexus/services/local_heal/protocol.py` — 收斂到 OutputUnderstandingResult
- `nexus/services/local_heal/local_model_executor.py` — 改用 candidate 而非 raw text
- `tests/unit/local_heal/test_output_understanding.py` — **NEW**: full coverage

---

## Phase 2: Apply / Hash / Anchor Truth

### Hash Chain

```
raw_output_hash (sha256 of raw model output)
    ↓ normalize
normalized_patch_hash (sha256 after normalization)
    ↓ apply
applied_patch_hash (sha256 of actual workspace diff)
```

### Rules

1. `selected_candidate_hash_matches_applied == True` → 才能 claim solved
2. `verifier_pass && hash_mismatch` → `model_output_verifier_passed` (not solved)
3. Source anchor 必須包含 `target_file`, `target_symbol`, `line_span`, `old_block_hash`
4. Hash mismatch 時 receipt 阻擋 `claim_eligible`

### 受影響檔案

- `nexus/services/local_heal/isolated_workspace_apply.py`
- `nexus/services/local_heal/local_model_executor.py`
- `nexus/services/local_heal/isolated_local_solve_loop.py`

---

## Phase 3: Local-First Cascade

### Topology: `local_first_cascade`

```
ornith:9b (28s, ~500 tokens)
  └→ verifier PASS? → Done. receipt: solved_by_first_model
  └→ verifier FAIL → qwythos:9b (27s, reasoning, different strengths)
      └→ verifier PASS? → Done. receipt: solved_by_second_model
      └→ verifier FAIL → 14b model (or cloud, if available)
          └→ receipt: escalated_to_large
```

### 預期效益

- 多數簡單修復：28s 完成，500 tokens
- 平均延遲低於 committee（200s）
- Token 節省 30-50%（不叫多模型時）

### 受影響檔案

- `nexus/engine/capability_planner.py` — 新增 topology 選項
- `nexus/engine/local_model_policy.py` — cascade 模型選擇
- `nexus/services/local_heal/local_model_executor.py` — cascade 執行邏輯

---

## Phase 4: Committee as Routed Tool

### 啟用條件（AND）

- 第一次 local verifier fail
- candidate anchor ambiguous
- cross-file / multi-hop edit
- primary model 和 secondary model 給出不同修法
- router 判定 high ambiguity

### 停用條件

- 單一 model 已 pass verifier
- simple single-function fix
- candidate hash 完全匹配

### 關鍵規則

- committee 比較 `CanonicalPatchCandidate`，不比較 raw text
- Borda winner 不能繞過 verifier/apply/hash
- diversity selection 只在候選足夠多時啟用
- zero-winner → fail closed，不 fallback

---

## Phase 5: Hybrid Committee (Cloud + Local)

### 觸發條件

```
hard_case == True || ambiguity_high == True
```

### 流程

```
hard task
  → cloud candidate + ornith:9b + qwythos:9b (平行)
  → normalize all to CanonicalPatchCandidate
  → diversity / Borda
  → isolated apply
  → verifier
  → receipt
```

### 預期效益

- Cloud 保上限（解決最難的 bug）
- Local 提供不同解法（diversity 避免 common wrong answer）
- Receipt 能證明 cloud/local 哪個 candidate 被選

---

## Phase 6: Difficulty Router (RouteJudge v2)

### 輸入信號

| 信號 | 來源 |
|------|------|
| task size | benchmark spec |
| target span size | locked_search |
| verifier availability | route_context |
| previous failure class | learning_closure |
| source anchor confidence | canonical candidate |
| candidate conflict | committee vote |
| model history by task class | telemetry |

### 輸出路線

| 路線 | 使用時機 |
|------|---------|
| `local_only` | Easy, single-function |
| `local_first_cascade` | Default |
| `local_committee` | High ambiguity |
| `hybrid_committee` | Hard case |
| `cloud_direct` | No local model available |
| `human_review_required` | Claim gate blocked |

---

## Phase 7: Larger Heldout

### 規格

- 30-50 題 heldout
- 每題標註 failure class
- 對比所有 route
- 每次失敗歸因到：model capacity / output understanding / anchor/apply / verifier harness / memory distractor / candidate arbitration

### 完成條件

- 每個 route 都有同一套 receipt schema
- `public_claim_allowed == false` 直到完整 gate 通過
- 下一輪開發只修 top failure class

---

## Phase 8: Governance & Documentation

### 產出

1. **ADR**: `Nexus Repair Mainline: Model Proposes, Nexus Verifies`
2. **Route Policy Table**: 每個 route 的啟用條件、authority、claim boundary
3. **Claim Boundary**: 什麼能說 solved，什麼只能說 model_output_passed

### 統一詞彙表

| 詞彙 | 定義 |
|------|------|
| `model_output_passed` | 模型產出有效 patch |
| `patch_applied` | patch 成功套用到 workspace |
| `hidden_verifier_passed` | 測試通過 |
| `claim_eligible` | 以上三項全部成立 |

---

## 總執行順序

```
P0  現況分組 ─────────────────── 現在
P0.5 needs_recheck split ─────── P1 前置條件：isolated_workspace_apply.py + local_model_executor.py 先拆完
P1   CanonicalPatchCandidate ──── 第 1 包
P2   apply/hash/anchor truth ──── 第 2 包
P3   local-first cascade ──────── 第 3 包
P4   routed local committee ───── 第 4 包
P5   hybrid committee ─────────── 第 5 包
P6   difficulty router ────────── 第 6 包
P7   larger heldout ───────────── 第 7 包
P8   ADR / policy / claim gate ── 第 8 包
```

**不能跳的關鍵**:

- P0.5 是前提：`needs_recheck` 未拆完之前不能開 P1。拆分假設「有疑慮視為 experiment」，不搶進 mainline。
- P1 是地基：沒有 canonical candidate，後面的 committee 和 hybrid 都在比 raw text
- P2 是誠實：hash mismatch 不解決，所有「成功」數字都虛
- P3 是預設路徑：大多數修復不需要 committee
- P4/P5 是高級能力，在 P1-P3 穩定之前不要碰

---

## Appendix: Nexus 當前狀態對照

| 維度 | 當前狀態 | 目標狀態 |
|------|---------|---------|
| Topology | dirty-tree legacy default: `local_committee_only` | mainline target: `local_first_cascade` |
| Model output | Raw text, 格式各異 | CanonicalPatchCandidate |
| Hash | Multiple, 不完全一致 | chain: raw→normalized→applied |
| Committee | Default topology | Routed hard-case tool |
| Cloud hybrid | ❌ 未實作 | Available in P5 |
| Route decision | Env var 手動 | RouteJudge v2 (P6) |
| Heldout | ~10 tasks | 30-50 tasks |
| Documents | 分散 | ADR + Route Policy + Claim Boundary |
