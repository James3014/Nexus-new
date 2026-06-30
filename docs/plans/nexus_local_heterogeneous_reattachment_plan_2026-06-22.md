# Nexus 本地異構模型接回 `with_nexus` 主路徑完整計劃

**日期**: 2026-06-22  
**用途**: 提供給後續 Agent / Gemini / LocalHeal 實作者作為執行規格。  
**狀態裁決**: `LOCAL_HETEROGENEOUS_WITH_NEXUS_REATTACHMENT_PLAN_v1`  
**總目標**: 將 6 月本地模型 / U3 / Memory / Patch Protocol / Local Portfolio 優化，接回 5 月已驗證過的 `with_nexus` 主路徑，使本地模型能穿完整 Nexus armor 執行。  
**治理邊界**: `public_claim_allowed=false`, `production_ready=false`, `training_export_allowed=false`, `internal_only=true`

---

## 0. 核心裁決

目前不能再把問題描述成「Nexus 沒有主路由」。5 月 `Gemini + Nexus` 已經有明確 `with_nexus` 主路徑，核心在：

```text
scripts/bench/capability_ab_runner.py
```

5 月的主路徑特徵是：

```text
with_nexus vs without_nexus
subprocess / inprocess runner
hidden verifier
run eligibility
route decision
evidence bundle
model_uses_nexus
nexus_context_delivered
claim gate
trust mismatch gate
public report
```

6 月後來做了很多本地模型優化，但分散在 LocalHeal、U3 receipts、AG5/AB3/BD reports、Memory-EVAL、patch protocol 等線上，沒有穩定接回 5 月的 `capability_ab_runner.py` with_nexus 主路徑。

因此真正目標不是「從零建立主路由」，而是：

```text
將 6 月 local model / U3 / memory / patch protocol 優化
接回 5 月 capability_ab_runner.py 的 with_nexus 主路徑。
```

---

## 1. 不可混淆的四條線

### 1.1 5 月 `with_nexus` 主路徑

代表檔案：

```text
scripts/bench/capability_ab_runner.py
scripts/bench/ab_eval.py
scripts/bench/evidence_bundle_manifest.py
scripts/bench/benchmark_eligibility.py
docs/reports/GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-05-01.md
docs/reports/NEXUS_PUBLIC_VALUE_COMPARISON_2026-05-01.md
docs/reports/NEXUS_ROUTING_V5_P12_GEMINI_FLASH_LANES_2026-05-02.md
docs/reports/NEXUS_PUBLICATION_READY_12X2_SUMMARY_2026-05-20.md
```

已知能力：

```text
same-model A/B
Gemini bare vs Gemini wearing Nexus
hidden verifier
route_decision_schema_version
model_uses_nexus_rate
nexus_context_delivered_rate
claim_verified_rate
artifact hash evidence
public claim gate
```

代表結果：

```text
Gemini 3 Flash bare: 8/12 verified, 66.7%
Gemini 3 Flash + Nexus: 12/12 verified, 100%
Public claim gate: PASS

Publication-ready 12x2:
Gemini bare: 16/24 verified, 66.7%
Gemini + Nexus: 24/24 verified, 100%
```

限制：

```text
目前 checkout 沒找到當時 .nexus/reports/... 原始 evidence bundle。
後續若要 public/repro claim，需要找回或重跑 evidence bundle。
```

### 1.2 6 月本地模型 / U3 / local portfolio 優化

代表檔案：

```text
nexus/engine/local_model_policy.py
nexus/services/local_heal/committee_orchestrator.py
nexus/services/local_heal/backend_resource_policy.py
nexus/services/local_heal/role_contract.py
nexus/services/local_heal/native_route_adapter.py
nexus/services/local_heal/targeted_fallback.py
nexus/services/local_heal/action_protocol.py
nexus/services/local_heal/source_hash_guard.py
nexus/services/local_heal/ast_locator.py
nexus/services/local_heal/patch_intent.py
docs/reports/local_model_policy_packet_only_commit_gate_v0.md
docs/reports/nexus_local_qwen_repair_unified_handoff_20260619.md
docs/reports/ag5_local_portfolio_optimization_decision_v0.md
docs/reports/ab3_local_model_full_power_decision_v0.md
docs/reports/bd_local_nexus_ceiling_discovery_benchmark_v0.md
docs/reports/r2_model_acquisition_microbenchmark_v0.md
docs/reports/r4_external_model_selection_decision_v0.md
artifacts/runtime/u3_expanded_heterogeneous_route_benchmark_v0/
```

6 月成果包含：

```text
LocalModelPolicy v2.2
3B gate + critic + evidence judge
Qwen 7B proposer
DeepSeek 6.7B proposer
bucket-specific primary proposer
disagreement-triggered secondary proposer
targeted 14B fallback
action protocol expansion
source_hash_guard
ast_locator
patch_intent
line-span evidence
evidence context compression direction
Learning Closure / Meta-Opt direction
```

注意：這些成果很多是 report / artifact / local runtime 層證據，不代表已接回 5 月 `with_nexus` runner。

### 1.3 MEMORY-EVAL 線

代表檔案：

```text
scripts/eval/run_memory_eval_9_real_model_ab.py
scripts/eval/run_memory_eval_11_c13453_real_model_ab.py
tests/unit/local_heal/test_memory_eval_9_real_model_influence_ab.py
tests/unit/local_heal/test_memory_eval_11_c13453_real_model_ab.py
```

定位：

```text
diagnostic memory transport / prompt influence experiment
```

不是：

```text
full Nexus armor
U3 local heterogeneous runtime
5 月 with_nexus main route
```

不可再把 MEMORY-EVAL 當主線進度。

### 1.4 目前 U3 scaffold

目前 U3 scaffold 大致做到：

```text
deepseek-coder:6.7b-instruct allowlist scaffold
judge / proposer / secondary_proposer role contract
explicit U3 route profile
committee trace
committee_model_override
receipt.telemetries.committee
selected-non-applied fail-closed guard
focused tests
```

目前仍不能宣稱：

```text
full U3 route wired
candidate isolation complete
selected candidate re-applied correctly
AG5 route preserved
memory decision layer wired
5 月 with_nexus runner reattached
public claim allowed
production ready
```

---

## 2. 現況 MCP 查證重點

### 2.1 `capability_ab_runner.py` 已有 Ollama provider

目前 `scripts/bench/capability_ab_runner.py` 已有：

```text
--with-model-provider choices=[gemini, codex, ollama]
```

當 `--with-model-provider ollama` 時，runner 會設定：

```text
NEXUS_OAUTH_PROVIDER=ollama
NEXUS_OLLAMA_ACTIVE_MODEL
NEXUS_OLLAMA_MODEL
NEXUS_GEMINI_MODEL_NAME = ollama model name
```

因此，不建議第一步新增：

```text
--backend_profile=local_heterogeneous
```

更合理的接法是沿用現有 provider：

```text
--with-model-provider ollama
```

再用 route/profile/env 啟用本地異構路由，例如：

```text
NEXUS_USE_COMMITTEE=1
NEXUS_LOCAL_ROUTE_PROFILE=qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b
NEXUS_OLLAMA_ROUTE=local_heterogeneous
```

具體 env 名稱可在實作前再定，但原則是：

```text
不要重造 runner provider abstraction；
先擴充既有 with_model_provider=ollama 路徑。
```

### 2.2 `CommitteeOrchestrator` 目前仍是固定雙 proposer scaffold

目前 `committee_orchestrator.py` 中可見固定 proposer specs：

```text
qwen2.5-coder:7b-instruct
deepseek-coder:6.7b-instruct
```

它透過 `NEXUS_USE_COMMITTEE=1` 啟用，並在同一個 `ctx` 中連續執行 patch phase。

問題：

```text
沒有 candidate isolation
沒有 clean baseline reset
沒有 selected candidate re-apply
固定雙跑，尚未保留 AG5 bucket-specific / disagreement-triggered semantics
```

目前 fail-closed guard 是必要但不完整。

### 2.3 Memory adapter 已有 transport，但不是 decision layer

目前 `MemoryRetrievalAdapter` 支援：

```text
LocalJsonlLessonStore
FindingsMemoryLessonStore
MemoryRepositoryLessonStore
```

`NativeEvidencePacketBuilder` 也會抽 memory evidence 進 evidence packet。

但目前未證明 memory 會影響：

```text
task bucket
primary proposer selection
second proposer trigger
14B fallback trigger
DDTree / Autoreason pruning
repair strategy
```

所以 memory decision layer 仍未接。

### 2.4 TargetedFallbackGate 存在，但未接入 committee

`nexus/services/local_heal/targeted_fallback.py` 已有：

```text
TargetedFallbackGate
failure_class == MODEL_SEMANTIC_LIMIT
NEXUS_14B_RESOURCE_BLOCKED guard
NEXUS_REAL_FALLBACK_PROBE optional Ollama tags check
```

但目前 committee path 未證明會呼叫它。

### 2.5 ActionProtocol 存在，但 committee path 未證明經過它

`nexus/services/local_heal/action_protocol.py` 已有：

```text
ProtocolAction
ActionProtocol
validate_protocol
apply_transactional
rollback
TWO_FILE_COORDINATED_EDIT owner approval
MULTI_STEP_LOCAL_EDIT
BOUNDED_CROSS_FILE_EDIT
DEPENDENT_SYMBOL_UPDATE
```

但目前 U3 committee candidate 生成未證明一定經過：

```text
source_hash_guard
ast_locator
patch_intent
action_protocol
deterministic applier
rollback protection
```

---

## 3. 完整執行計劃

## Phase 0：工作樹與任務邊界鎖定

**目標**: 避免把 unrelated dirty artifacts / pycache / MEMORY-EVAL runtime 輸出混進任務。

### 檢查項

```bash
git status --short
git diff --stat
git diff --name-only
```

### 禁止 stage

```text
artifacts/
scratch/
__pycache__/
*.pyc
MEMORY-EVAL runtime artifacts
AO2 / AV / eval_substrate artifacts
unrelated report outputs
```

### 允許候選 scope

視任務階段而定，通常限制在：

```text
nexus/services/local_heal/
nexus/engine/local_model_policy.py
scripts/bench/capability_ab_runner.py
scripts/bench/evidence_bundle_manifest.py
tests/unit/local_heal/
tests/unit/engine/
```

### Exit Gate

```text
Agent must explicitly list intended file touch set before editing.
No broad refactor.
No git add -A.
No benchmark before unit/smoke gates.
```

---

## Phase 1：Preservation Audit（不改 code）

**目標**: 確認目前 U3 scaffold 是否旁路 6 月優化與 5 月主路徑。

### 1.1 查核檔案

```text
scripts/bench/capability_ab_runner.py
nexus/engine/local_model_policy.py
nexus/services/local_heal/committee_orchestrator.py
nexus/services/local_heal/backend_resource_policy.py
nexus/services/local_heal/role_contract.py
nexus/services/local_heal/native_route_adapter.py
nexus/services/local_heal/phases/patch_synthesis.py
nexus/services/local_heal/memory_retrieval_adapter.py
nexus/services/local_heal/native_evidence_packet.py
nexus/services/local_heal/targeted_fallback.py
nexus/services/local_heal/action_protocol.py
nexus/services/local_heal/source_hash_guard.py
nexus/services/local_heal/ast_locator.py
nexus/services/local_heal/patch_intent.py
nexus/services/local_heal/learning_closure_bridge.py
docs/reports/ag5_local_portfolio_optimization_decision_v0.md
docs/reports/ab3_local_model_full_power_decision_v0.md
docs/reports/bd_local_nexus_ceiling_discovery_benchmark_v0.md
docs/reports/local_model_policy_packet_only_commit_gate_v0.md
docs/reports/nexus_local_qwen_repair_unified_handoff_20260619.md
```

### 1.2 必答問題

對每項標記 `PRESERVED / PARTIAL / LOST / NOT_APPLICABLE`：

```text
LocalModelPolicy decision metadata 是否保留？
qwen2.5-coder:7b-instruct 是否 allowlisted？
deepseek-coder:6.7b-instruct 是否 allowlisted？
committee_model_override 是否旁路 retry / timeout / sidecar / 14B fallback？
3B 是否真作為 gate + critic + evidence judge？
是否固定雙跑 Qwen+DeepSeek？
是否保留 bucket-specific primary proposer？
是否保留 disagreement-triggered second proposer？
是否有 candidate isolation？
是否有 selected candidate re-apply？
是否證明 selected_candidate_hash == applied_patch_hash？
是否走 source_hash_guard？
是否走 ast_locator？
是否走 patch_intent？
是否走 action_protocol / deterministic applier？
是否走 verifier / sandbox / ultra review？
是否寫 claim/delivery gate？
是否寫 learning closure？
memory 是否只進 prompt？
memory 是否影響 route/bucket/proposer/fallback？
是否接到 capability_ab_runner.py with_nexus path？
```

### 1.3 輸出

```text
docs/reports/u3_with_nexus_preservation_audit_v0.md
artifacts/runtime/u3_with_nexus_preservation_audit_v0/preservation_matrix.json
artifacts/runtime/u3_with_nexus_preservation_audit_v0/required_fixes.json
```

### 1.4 Gate

```text
No code changes.
No model calls.
No benchmark.
No public claim.
```

---

## Phase 2A：Candidate Isolation + Selected Re-Apply（最小語義正確閉環）

**目標**: 修正目前 committee route 最大 blocker：兩個 proposer 必須從同一乾淨基線產生候選，最後只套用 judge 選中的候選。

### 2A.1 需求

同一個 LocalHeal/Nexus runtime run 必須做到：

```text
1. Capture clean baseline hash / source hash.
2. Run Qwen candidate from clean baseline.
3. Persist Qwen raw output + parsed patch + patch hash.
4. Reset to clean baseline.
5. Run DeepSeek candidate from clean baseline.
6. Persist DeepSeek raw output + parsed patch + patch hash.
7. 3B judge / committee selector selects one candidate.
8. Reset to clean baseline.
9. Apply selected candidate only.
10. Verifier runs.
11. Receipt proves selected_candidate_hash == applied_patch_hash.
```

### 2A.2 建議觸碰檔案

最多 5 個：

```text
nexus/services/local_heal/committee_orchestrator.py
nexus/services/local_heal/receipt.py
nexus/services/local_heal/interface.py
tests/unit/local_heal/test_committee_route_trace.py
tests/unit/local_heal/test_committee_candidate_isolation.py  # new if needed
```

若已有合適測試檔，優先擴充現有 `test_committee_route_trace.py`，避免新檔爆炸。

### 2A.3 Receipt fields

必須新增或驗證存在：

```json
{
  "telemetries": {
    "committee": {
      "schema": "nexus.local_heal.committee_trace.v1",
      "route_policy": "qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b",
      "candidate_isolation": {
        "enabled": true,
        "baseline_hash": "...",
        "qwen_candidate_hash": "...",
        "deepseek_candidate_hash": "...",
        "selected_candidate_hash": "...",
        "applied_patch_hash": "...",
        "selected_candidate_hash_matches_applied": true
      },
      "proposer_candidates": [],
      "judge_selection": {},
      "committee_receipt": {}
    }
  }
}
```

### 2A.4 Tests

```bash
uv run pytest tests/unit/local_heal/test_committee_route_trace.py tests/unit/local_heal/test_role_contract.py tests/unit/local_heal/test_native_route_adapter.py -q
```

若新增 isolation 測試：

```bash
uv run pytest tests/unit/local_heal/test_committee_candidate_isolation.py -q
```

### 2A.5 Gate

```text
No real Ollama required.
No benchmark.
No public claim.
Candidate isolation must be unit-test proven.
If selected candidate cannot be re-applied, fail closed.
```

---

## Phase 2B：Policy Preservation Fix

**目標**: 確認 committee route 不會旁路 `LocalModelPolicy` 和 resource policy。

### 2B.1 必修問題

```text
qwen2.5-coder:7b-instruct 是否在 backend_resource_policy.py allowlist？
deepseek-coder:6.7b-instruct 是否在 backend_resource_policy.py allowlist？
qwen2.5-coder:3b-instruct 是否在 role/resource policy 裡作 judge？
committee_model_override 是否保留 LocalModelPolicy:
  - policy_version
  - reason_code
  - timeout_seconds
  - ollama_options
  - selected_model_source
  - override_reason
  - fallback_eligible
```

### 2B.2 建議觸碰檔案

最多 4 個：

```text
nexus/services/local_heal/backend_resource_policy.py
nexus/services/local_heal/role_contract.py
nexus/services/local_heal/phases/patch_synthesis.py
tests/unit/local_heal/test_role_contract.py
```

### 2B.3 Gate

```text
No hardcoded model bypass without policy trace.
No unknown model accepted silently.
No 14B fallback semantics erased.
Sidecar remains shadow-only.
```

---

## Phase 2C：AG5 Route Semantics（延後，不與 2A 同做）

**目標**: 將 fixed dual proposer 改為 AG5 的 cost-optimized semantics。

### 2C.1 必須先回答

先查是否已有可復用 runtime 實作：

```text
AG5BucketClassifier 是否存在？
task bucket classification 是否已有函數？
route_cost_controls 是否可復用？
disagreement-triggered second proposer 是否已有策略物件？
```

若沒有現成實作，不要假裝「接線」。應明確標為 new policy implementation based on AG5 report。

### 2C.2 AG5 semantics

```text
3B = gate + critic + evidence judge
default = cost-optimized route
easy/simple = single primary proposer
medium/hard/high uncertainty = possible second proposer
second proposer = disagreement-triggered, not always-on
complex/hard = hard-task route
```

### 2C.3 Gate

```text
Do not force dual proposer on every task unless explicitly in diagnostic mode.
Must record why second proposer was or was not invoked.
```

---

## Phase 2D：Targeted 14B Fallback（延後）

**目標**: 只在符合條件時接入 14B fallback。

### 2D.1 可復用檔案

```text
nexus/services/local_heal/targeted_fallback.py
nexus/engine/local_model_policy.py
```

### 2D.2 條件

```text
failure_class == MODEL_SEMANTIC_LIMIT
verifier_available == true
armor_active == true
resource guard allows
NEXUS_14B_RESOURCE_BLOCKED != true
NEXUS_DISABLE_14B_RETRY != 1
```

### 2D.3 Gate

```text
14B fallback is never default.
Resource blocked must fail closed / skip cleanly.
Fallback attempt must be receipt-backed.
```

---

## Phase 2E：Patch Protocol / Source Guard Preservation（延後）

**目標**: 確保 committee selected candidate 不會繞過安全修補協議。

### 2E.1 必經能力

```text
patch_intent
source_hash_guard
ast_locator
action_protocol
deterministic applier
rollback protection
verifier
```

### 2E.2 Gate

```text
No fuzzy patch shortcut.
No selected patch apply without source hash validation.
No multi-file edit without action protocol constraints.
```

---

## Phase 3：Attach to existing `with_model_provider=ollama` path

**目標**: 不新增 `backend_profile`，先把本地異構路由接到現有 `capability_ab_runner.py --with-model-provider ollama`。

### 3.1 推薦 CLI smoke

```bash
NEXUS_USE_COMMITTEE=1 \
NEXUS_LOCAL_ROUTE_PROFILE=qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b \
uv run python scripts/bench/capability_ab_runner.py \
  --nexus-only \
  --with-model-provider ollama \
  --with-llm-mode all \
  --with-nexus-runner subprocess \
  --enable-hidden-verifier \
  --max-tasks 3 \
  --timeout-sec 120 \
  --output-dir .nexus/reports/local_heterogeneous_with_nexus_smoke_v0
```

具體 env 名稱可調，但不得重造 runner 主路徑。

### 3.2 Runner evidence 必須記錄

```text
with_model_provider=ollama
ollama_active_model
NEXUS_USE_COMMITTEE=1
route_profile
committee_trace present
memory_trace present
route_decision_present
model_uses_nexus=true
nexus_context_delivered=true
hidden_verifier_mode=true
claim gate result
trust mismatch result
```

### 3.3 可觸碰檔案

Phase 3 才考慮碰：

```text
scripts/bench/capability_ab_runner.py
scripts/bench/evidence_bundle_manifest.py
tests/benchmark/test_capability_ab_runner.py 或既有 runner tests
```

### 3.4 Gate

```text
3-task smoke only.
No BD 35-task benchmark.
No public claim.
No production_ready.
Must produce evidence bundle.
```

---

## Phase 4：Memory Decision Layer（接線，不是 prompt injection）

**目標**: 讓 memory 從 evidence/prompt 升級為 conservative route signal。

### 4.1 先做最保守決策

不要一開始讓 memory 直接選模型或觸發 14B。先只允許：

```text
memory_hard_signal=true → enable second proposer / candidate_cap=2
memory_known_failure_pattern=true → mark task as higher uncertainty
```

### 4.2 需要 quality gate

新增或定義：

```text
memory_signal_quality_gate
```

Memory lesson 至少要滿足：

```text
provenance exists
task/failure class matches
relevance_score >= threshold
not merely outcome marker
has actionable repair/failure pattern
```

### 4.3 可觸碰檔案

```text
nexus/services/local_heal/memory_retrieval_adapter.py
nexus/services/local_heal/native_evidence_packet.py
nexus/services/local_heal/reasoning_advisory_bridge.py
nexus/services/local_heal/committee_orchestrator.py
tests/unit/local_heal/test_bmf3_nexus_memory_integration.py
```

### 4.4 Gate

```text
Memory can increase caution; memory cannot alone mark solved.
Memory can trigger second proposer; memory cannot alone trigger 14B in first version.
Memory signal must be receipt-backed.
```

---

## Phase 5：Ceiling Eval（最後才做）

**前置條件**:

```text
Phase 2A candidate isolation PASS
Phase 2B policy preservation PASS
Phase 3 with_model_provider=ollama smoke PASS
evidence bundle complete
committee trace complete
hidden verifier available
```

### 5.1 先小批

```text
3 tasks → 5 tasks → 10 tasks
```

### 5.2 再重跑 BD model-relevant subset

只在小批通過後才跑：

```text
BD 35 model-relevant tasks
```

### 5.3 指標

```text
solve_count
verified_count
candidate_isolation_pass_rate
selected_hash_matches_applied_rate
model_calls
latency
memory decision influence count
second proposer trigger count
14B fallback trigger count
trust_mismatch
claim gate result
```

### 5.4 Claim boundary

預設：

```text
public_claim_allowed=false
production_ready=false
training_export_allowed=false
internal_only=true
```

任何 public claim 必須另行審查。

---

## 4. 認同 / 不認同 Opus 計劃的部分

### 認同

```text
1. 核心問題是零件沒總裝，不是缺零件。
2. Phase 1 Preservation Audit 必須先做。
3. Candidate isolation 是 U3 runtime 的真正 blocker。
4. Memory 應該升級成 decision layer，不是只 append prompt。
5. 最終要接回 5 月 with_nexus 主路徑。
6. Ollama health check / model availability 是必要 preflight。
7. AG5 bucket classifier 是否存在是關鍵未知。
8. 5 月原始 bundle 不在 checkout，後續結果會是新 evidence。
```

### 不認同 / 需修正

```text
1. 不應優先新增 --backend_profile=local_heterogeneous。
   應沿用現有 --with-model-provider ollama。

2. Phase 2 scope 過大。
   AG5 + 14B + isolation + patch protocol 不應一次做。

3. AG5 bucket-specific route 不一定已有現成 runtime 實作。
   需要先查，找不到就不能叫接線。

4. Memory decision layer 難度被低估。
   必須有 memory quality gate。

5. Phase 5 太早。
   BD 35-task ceiling 不應在 runner smoke 前跑。

6. Verification command 部分不準。
   目前存在的是 test_committee_route_trace.py，不是 test_committee_orchestrator.py。
```

---

## 5. 修正版最小可行路徑

如果時間有限，真正最小路徑是：

```text
Phase 1 Preservation Audit
↓
Phase 2A Candidate Isolation + Selected Re-Apply
↓
Phase 2B Policy Preservation
↓
Phase 3 Attach to with_model_provider=ollama 3-task smoke
```

不要先做：

```text
Memory full decision layer
AG5 complete optimization
14B fallback
BD 35-task benchmark
public claim
```

---

## 6. Agent 固定指令模板

後續可貼給 agent：

```text
Task:
Implement the next step of local heterogeneous route reattachment.

Context:
Nexus already has a proven May with_nexus route via scripts/bench/capability_ab_runner.py.
Do not create a separate benchmark path unless explicitly required.
Do not use MEMORY-EVAL scripts as the mainline.
Do not treat manual receipts or reports as runtime success.

Current goal:
Attach June local model / U3 / memory / patch protocol work back to the May with_nexus path.

Non-negotiable:
- No Qwen-only shortcut.
- No memory-only eval.
- No report-only success claim.
- No manual receipt treated as runtime.
- No public claim unless hidden verifier and claim gate pass.
- No git add -A.
- No unrelated artifacts in commit.
- Preserve LocalModelPolicy v2.2 and AG5/AB3/BD semantics where applicable.

Near-term priority:
1. Preservation audit first.
2. Candidate isolation second.
3. Policy preservation third.
4. Reattach through existing --with-model-provider ollama path.
5. Only then run small smoke.
```

---

## 7. Final verdict

```text
OPUS_PLAN_DIRECTION_ACCEPTED_WITH_MAJOR_SCOPE_AND_ENTRYPOINT_REVISIONS
```

最關鍵修正：

```text
不要新增 backend_profile 重造 runner。
先把 U3/local heterogeneous route 接到現有 --with-model-provider ollama 的 with_nexus 路徑。
```

最重要短期 blocker：

```text
Candidate isolation + selected candidate re-apply.
```

最重要架構 blocker：

```text
Memory 目前仍是 transport/evidence 層，還不是 full route decision layer。
```

最重要治理邊界：

```text
目前全部仍為 internal-only。
不可宣稱 production ready 或 public claim。
```
