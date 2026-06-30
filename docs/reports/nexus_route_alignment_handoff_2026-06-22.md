# Nexus 主路由、6 月本地模型優化與 U3 / Memory 接線斷層報告

**日期**: 2026-06-22  
**用途**: 交接給後續 Agent / Gemini / LocalHeal 實作者，避免再次把 Nexus 主路由、6 月本地模型優化、MEMORY-EVAL、U3 heterogeneous route 混為一談。  
**狀態裁決**: `NEXUS_ROUTE_ALIGNMENT_REPORT_FOR_AGENT_HANDOFF`  
**Claim boundary**: `public_claim_allowed=false`, `production_ready=false`, `training_export_allowed=false`, `internal_only=true`

---

## 0. 最短結論

目前問題不是「Nexus armor 從來沒有主路由」，也不是「Nexus armor 測出來很弱」。

更準確的結論是：

```text
5 月 Gemini+Nexus 確實有一條明確的 with_nexus 執行路徑，
而且曾經證明同模型穿 Nexus 比 Gemini bare 強。

6 月後來做了大量本地模型 / U3 / local portfolio / patch protocol / memory 相關優化，
但這些成果沒有穩定收斂回 5 月那條 with_nexus capability runner / evidence bundle / route gate 主路徑。

後來 MEMORY-EVAL-9/11 又把主線跑偏成 Qwen 7B + MemoryRetrievalAdapter 的 isolated eval script。
目前 U3 scaffold 只是在 LocalHeal committee 層補一部分三模型路由骨架，
還不能等同於接回 5 月 Nexus 主路由，也不能等同於 6 月 full local portfolio + Nexus armor。
```

一句話：

```text
要做的不是從零重造 Nexus 主路由，
而是把 6 月 local model / U3 / memory / patch protocol 優化接回 5 月 with_nexus 主路徑。
```

---

## 1. 必須分清楚的四條線

### 1.1 5 月 Gemini+Nexus 主路徑

這條線的核心是：

```text
scripts/bench/capability_ab_runner.py
with_nexus vs without_nexus
same task A/B
hidden verifier
run eligibility
evidence bundle
route decision
model_uses_nexus
nexus_context_delivered
claim gate
trust mismatch gate
public report
```

這是「Gemini bare」和「Gemini wearing Nexus」的主要比較路徑。

5 月報告中明確出現：

```text
without_nexus = gemini
with_nexus = subprocess + full capability stack
```

這代表它不是單純加 prompt，也不是 LocalHeal isolated eval。它是同一個 Gemini 透過 Nexus subprocess / capability stack / route decision / evidence bundle 執行。

重要報告與路徑：

```text
docs/reports/GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-05-01.md
docs/reports/NEXUS_PUBLIC_VALUE_COMPARISON_2026-05-01.md
docs/reports/NEXUS_ROUTING_V5_P12_GEMINI_FLASH_LANES_2026-05-02.md
docs/reports/NEXUS_PUBLICATION_READY_12X2_SUMMARY_2026-05-20.md
scripts/bench/capability_ab_runner.py
scripts/bench/ab_eval.py
scripts/bench/evidence_bundle_manifest.py
scripts/bench/benchmark_eligibility.py
```

5 月的代表性 claim：

```text
Gemini bare: 8/12 verified, 66.7%
Gemini + Nexus: 12/12 verified, 100%
Public claim gate: PASS
model_uses_nexus_rate: 100%
nexus_context_delivered_rate: 100%
claim_verified_rate: 100%
route_decision_present_rate: 100%
artifact_hash_count: 48
```

後續 12x2 publication-ready summary 又記錄：

```text
Gemini+Nexus: 24/24 verified delivery, 100%
Gemini bare: 16/24 verified delivery, 66.7%
trust mismatch: 0.0% both arms
public claim gate: PASS
performance claim gate: PASS
cost claim gate: PASS
```

注意：目前 checkout 中沒有找到 `.nexus/reports/bench_gemini3flash_value12x1_20260501_route_gate_public/...` 和 `.nexus/reports/publication_ready_value12x2_20260520/...` 這些 runtime evidence bundle 原始檔。它們可能未被保留在目前工作樹。但報告與 runner code 對得上，說明這條執行路徑不是憑空想像。

### 1.2 6 月本地模型 / Local Portfolio / U3 優化線

6 月不是只做一件事。它至少包含：

```text
LocalModelPolicy
3B judge / gate / critic / evidence judge
Qwen 7B proposer
DeepSeek 6.7B proposer
Dual proposer / heterogeneous route
AG5 optimized local portfolio
AB3 full Nexus route decision
BD local ceiling discovery
targeted 14B fallback
action protocol expansion
evidence context compression
patch protocol / source guard / AST locator
```

重要報告與檔案：

```text
nexus/engine/local_model_policy.py
docs/reports/local_model_policy_packet_only_commit_gate_v0.md
docs/reports/nexus_local_qwen_repair_unified_handoff_20260619.md
docs/reports/ab3_local_model_full_power_decision_v0.md
docs/reports/ag5_local_portfolio_optimization_decision_v0.md
docs/reports/bd_local_nexus_ceiling_discovery_benchmark_v0.md
docs/reports/r2_model_acquisition_microbenchmark_v0.md
docs/reports/r4_external_model_selection_decision_v0.md
docs/reports/t2_heterogeneous_experimental_route_v0.md
docs/reports/t3_expanded_heterogeneous_route_benchmark_v0.md
docs/reports/u3_expanded_heterogeneous_route_benchmark_v0.md
artifacts/runtime/u3_expanded_heterogeneous_route_benchmark_v0/
```

這條線證明：本地小模型/中模型穿 Nexus armor 有潛力，但它不等於 5 月 with_nexus runner 已自動接收所有這些新能力。

### 1.3 MEMORY-EVAL-9/11 線

這條線後來跑偏了。

它主要是：

```text
scripts/eval/run_memory_eval_9_real_model_ab.py
scripts/eval/run_memory_eval_11_c13453_real_model_ab.py
Qwen 7B only
MemoryRetrievalAdapter on/off
raw output hash
prompt delta
isolated eval script
HealOrchestrator(phases=[])
pre-populated final_patch / patch_applied
artifact writing
```

它不是 5 月的 with_nexus main route，也不是 6 月的 full local portfolio route。

MEMORY-EVAL-9/11 有價值，但只應定位為：

```text
diagnostic memory transport / prompt influence experiments
```

不應當作主線進度。

### 1.4 現在 U3-HETEROGENEOUS-ROUTE-LIFT scaffold

目前 agent 已開始做的 U3 scaffold 主要修改：

```text
nexus/services/local_heal/backend_resource_policy.py
nexus/services/local_heal/role_contract.py
nexus/services/local_heal/native_route_adapter.py
nexus/services/local_heal/committee_orchestrator.py
nexus/services/local_heal/phases/patch_synthesis.py
nexus/services/local_heal/receipt.py
nexus/services/local_heal/interface.py
tests/unit/local_heal/test_role_contract.py
tests/unit/local_heal/test_native_route_adapter.py
tests/unit/local_heal/test_committee_route_trace.py
```

目前它接上的只是：

```text
DeepSeek 6.7B policy allowlist scaffold
judge / proposer / secondary_proposer role contract scaffold
explicit U3 route metadata
committee trace
patch_synthesis committee_model_override
receipt.telemetries.committee
selected-non-applied candidate fail-closed guard
```

但它還不是完整 U3 runtime，更不是 5 月 with_nexus 主路徑。

---

## 2. 5 月 Gemini+Nexus 主路徑細節

### 2.1 主 runner

核心檔：

```text
scripts/bench/capability_ab_runner.py
```

它包含大量與 `with_nexus` 相關的邏輯，例如：

```text
run_with_nexus()
run_without_nexus()
with_nexus subprocess timeout
with_nexus file / without_nexus file JSONL
model_uses_nexus
nexus_context_delivered
route_decision_schema_version
claim gate
trust mismatch
evidence bundle manifest
public claim gate
```

這是 5 月證明 Nexus wearing 有效的主幹，不是 LocalHeal memory eval script。

### 2.2 報告證據

`GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-05-01.md` 的核心內容：

```text
Baseline: gemini-3-flash-preview bare
Treatment: gemini-3-flash-preview wearing Nexus
任務集: scripts/bench/public_benchmark_nexus_value_v1.json
規模: 12 題 x 1 trial
Hidden verifier: 開啟
Public claim gate: PASS
Infra invalid: 0 both arms
```

主要結果：

```text
Gemini bare solve rate: 66.7%
Gemini + Nexus solve rate: 100.0%
Semantic verified: 66.7% -> 100.0%
Trust mismatch: 0.0% -> 0.0%
Avg wall time: 32.57s -> 49.16s
Avg model calls: 1.00 -> 1.08
```

它還明確列出 Nexus 補足能力：

```text
test_repair: Hyper / Delivery Gate
docs_code_sync: CodeIntel / Memory
ops_research: Claim Gate / Delivery Gate
all tasks: route_decision_schema_version=nexus_route_decision_v1
```

`NEXUS_ROUTING_V5_P12_GEMINI_FLASH_LANES_2026-05-02.md` 又明確寫：

```text
比較: without_nexus=gemini vs with_nexus(subprocess + full capability stack)
固定條件: hidden verifier 開啟、同 task manifest、同輪次
```

所以：5 月主路徑是明確存在的。

### 2.3 目前限制

目前 workspace 沒有找到報告裡列出的 `.nexus/reports/...` evidence bundle 原始檔。因此：

```text
可承認：5 月有 report + runner code + 指標 + declared evidence path。
不可過度宣稱：目前 checkout 可直接重放那些原始 evidence bundle。
```

後續如果要做嚴格 public/repro claim，需要找回或重跑 5 月 evidence bundle。

---

## 3. 6 月 local model 優化細節

### 3.1 LocalModelPolicy v2.2

核心檔：

```text
nexus/engine/local_model_policy.py
```

它不是單純模型名設定，而是一套本地模型策略：

```text
planning/localization/reproduction: small model, usually Qwen 7B
patch first attempt: small model, usually Qwen 7B
patch retry: optional 14B escalation unless NEXUS_DISABLE_14B_RETRY=1
NAME_SANITY_ERROR: 14B precision retry
ALGEBRAIC reasoning: 14B precision
7B num_ctx default: 16384
14B patch num_predict: 3072
retry temperature scaling: attempt > 1 increases temperature up to 0.4
SidecarConfig: shadow-only, forbidden for patch/claim/verification
NEXUS_OLLAMA_MODEL legacy override guard
```

`local_model_policy_packet_only_commit_gate_v0.md` 記錄該次精準提交：

```text
local_model_policy.py only
Ollama patch prediction length 1024 -> 3072
SidecarConfig shadow-only added
py_compile PASS
commit hash: 95bf17d8
```

### 3.2 Patch protocol / source guard

`nexus_local_qwen_repair_unified_handoff_20260619.md` 記錄：

```text
M5 sealed at 10/12
patch_intent.py created
source_hash_guard.py created
ast_locator.py created
24/24 unit tests pass
line-span evidence improves hunk-offset stability
abbreviated_traceback pending
StrategyEnvelope trace-only pending
```

這些是 6 月本地模型解題時的安全與穩定性優化，不應被 U3 scaffold 旁路。

### 3.3 AG5 optimized local portfolio

`ag5_local_portfolio_optimization_decision_v0.md` 的核心結論：

```text
AG5_OPTIMIZED_3B_DUAL_7B_ROUTE_CONFIRMED

3B: Gate + critic + evidence judge
Dual 7B: Bucket-specific primary proposer + disagreement-triggered second
Nexus armor: Cost-optimized route for default, hard-task route for complex
```

這不是「每題固定跑 Qwen + DeepSeek」。AG5 的關鍵是：

```text
bucket-specific primary proposer
disagreement-triggered second proposer
cost-optimized default route
hard-task complex route
```

因此，若 U3 scaffold 固定永遠雙跑 Qwen/DeepSeek，就會退化，失去 AG5 的成本/延遲優化。

### 3.4 AB3 full Nexus route decision

`ab3_local_model_full_power_decision_v0.md` 的核心數據：

```text
Bare Local Model Baseline: 14.3% (2/14)
Single 7B Constrained: 21.4% (3/14)
Heterogeneous Route: 78.6% (11/14)
Control Plane v2: 85.7% (12/14)
Full Nexus Route: 85.7% (12/14), Avg Latency 35.0s
```

它定義「Full Nexus Route」包含：

```text
Pregate
CodeIntel AST Evidence Graph
Memory/LanceDB scoring
Autoreason/DDTree belief pruning
3B/7B/6.7B heterogeneous selection
Controlled Protocol
Deterministic Applier
Sandbox/Ultra Review
Meta-Opt / Learning Closure
```

重要邊界：

```text
public_claim_allowed=false
production_ready=false
training_export_allowed=false
internal_only=true
```

注意：AB3 是強報告，但要警惕它是否與 current executable route 一致。不能只因報告聲稱 full route 就當作 current LocalHeal runtime 已完整接上。

### 3.5 BD local ceiling

`bd_local_nexus_ceiling_discovery_benchmark_v0.md` 對最強本地路由做 ceiling 探測：

```text
3B judge + Qwen 7B + DeepSeek 6.7B + real Nexus armor
50 tasks total
35 model-relevant tasks
24/35 solved = 68.57%
15/15 deterministic health tasks PASS
```

失敗類型：

```text
MODEL_SEMANTIC_LIMIT
ACTION_PROTOCOL_LIMIT
EVIDENCE_SELECTION_LIMIT
MEMORY_RETRIEVAL_LIMIT
CORRECT_ABSTAIN
VERIFIER_LIMIT
```

下一步建議：

```text
targeted_14b_fallback
action_protocol expansion
evidence_context_compression
```

這說明：U3 是底座之一，但 6 月已經發現真正下一步不只是接回 U3，還要接回 action protocol、evidence compression、14B fallback、memory retrieval improvement 等能力。

---

## 4. MEMORY-EVAL-9/11 為何跑偏

### 4.1 它實際測的是什麼

MEMORY-EVAL-9/11 實際主要測：

```text
Qwen 7B
MemoryRetrievalAdapter
memory_on/off
prompt delta
raw output hash
patch hash
verifier result
```

它沒有測：

```text
5 月 with_nexus subprocess + full capability stack
3B judge
DeepSeek 6.7B proposer
dual proposer
AG5 optimized local portfolio
CodeIntel AST Evidence Graph
DDTree / Autoreason
Action Protocol / Source Guard
Sandbox / Ultra Review
Claim Gate as full delivery route
```

### 4.2 EVAL-11 代表性結果

EVAL-11 的本質：

```text
model: qwen2.5-coder:7b
memory_on retrieved 2 lessons
memory_off retrieved 0
prompt length changed
raw output hash unchanged
patch hash unchanged
verifier FAIL both
solved false both
```

因此它只能證明：

```text
memory retrieval/prompt transport worked
but no model decision delta
no patch delta
no outcome uplift
```

不能拿來說：

```text
Nexus armor weak
full route ineffective
memory full-route integration failed
```

因為它根本不是 full route。

### 4.3 Memory 的真問題

目前 memory 有接 transport layer，但沒有接成 full-route decision layer。

已接：

```text
retrieve
rank/select some lesson
inject into prompt
write memory trace
```

未證明接入：

```text
task bucket selection
primary proposer choice
second proposer trigger
evidence context compression
repair strategy
DDTree / Autoreason pruning
retry / fallback policy
learning closure quality loop
```

因此更精確說法：

```text
Memory transport layer 部分接好；
Memory decision layer / repair intelligence layer 尚未接入 5 月/6 月主路徑。
```

---

## 5. U3 scaffold 的目前狀態與風險

### 5.1 已接上的 scaffold

目前 U3 scaffold 已開始接：

```text
deepseek-coder:6.7b-instruct allowlist
judge/proposer/secondary_proposer role contract
explicit route profile qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b
manual_only_experimental / manual_invocation_only route metadata
committee proposer specs: Qwen 7B + DeepSeek 6.7B
candidate snapshot trace
model mismatch guard
selected candidate not applied fail-closed guard
committee_model_override in patch_synthesis
receipt.telemetries.committee
focused unit tests
```

這是正確方向，但只能叫：

```text
U3_HETEROGENEOUS_ROUTE_LIFT_PHASE_1_SCAFFOLD_PARTIAL
```

### 5.2 不能宣稱的東西

目前不能宣稱：

```text
full U3 route wired
3B judge truly invoked as gate/critic/evidence judge
Qwen + DeepSeek candidate isolation works
selected candidate re-applied from clean baseline
full Nexus armor route runs
5 月 with_nexus runner now uses U3 route
6 月 AG5 optimized local portfolio preserved
verifier solved uplift
production_ready
public_claim_allowed
```

### 5.3 明確風險：旁路 6 月優化

目前 scaffold 可能退化成：

```text
fixed Qwen + DeepSeek committee scaffold
```

而不是：

```text
AG5 optimized local portfolio + AB3 full Nexus route + BD ceiling path
```

主要風險：

```text
committee_model_override 可能旁路 LocalModelPolicy 完整 decision trace
qwen2.5-coder:7b-instruct 是否 allowlisted 需確認
fixed dual proposer 可能丟掉 bucket-specific / disagreement-triggered second
candidate generation 未證明走 source_hash_guard / ast_locator / action_protocol
candidate isolation 未完成
selected candidate re-apply 未完成
Sandbox / Ultra Review / Claim Gate / Learning Closure 未證明完整接入
14B targeted fallback 未保留
evidence context compression 未保留
```

---

## 6. 正確架構圖：應該接回哪條路

### 6.1 不是重新造主路由

錯誤理解：

```text
Nexus 沒主路由，所以要從零建 full route。
```

正確理解：

```text
5 月已經有 with_nexus 主路由 / capability A-B runner。
現在要把 6 月本地模型、U3、memory、patch protocol 優化接回這條主路由。
```

### 6.2 正確總線

目標應該是：

```text
scripts/bench/capability_ab_runner.py / with_nexus 主路徑
    ↓
Nexus route decision / evidence bundle / hidden verifier / claim gate
    ↓
Local model backend option: 3B judge + Qwen 7B + DeepSeek 6.7B + optional 14B fallback
    ↓
AG5 local portfolio policy:
    - 3B gate + critic + evidence judge
    - bucket-specific primary proposer
    - disagreement-triggered second proposer
    - cost-optimized default / hard-task complex route
    ↓
CodeIntel / Memory / LanceDB / DDTree / Autoreason
    ↓
Controlled Protocol / source_hash_guard / ast_locator / action_protocol
    ↓
Deterministic applier / verifier / sandbox / ultra review
    ↓
Claim gate / Delivery gate / Learning closure
```

### 6.3 Agent 要避免的錯誤

禁止把以下任一條當作主線成功：

```text
isolated MEMORY-EVAL success
Qwen-only success
manual receipt success
report-only success
committee trace exists
model policy allowlist exists
role contract exists
```

以上都只是局部條件，不是 full route 成功。

---

## 7. 後續 agent 的判斷準則

### 7.1 接線驗證問題

Agent 每次協助時，先問：

```text
這個改動接的是 5 月 with_nexus 主路徑，還是只接 LocalHeal isolated path？
```

若只接 LocalHeal isolated path，要明確標為 scaffold / diagnostic，不能標為主路由成功。

### 7.2 必須保存的 6 月優化

後續 U3 / memory / local route 接線必須保留：

```text
LocalModelPolicy v2.2 decision metadata
ctx16k / num_predict / timeout / retry temperature scaling
Sidecar shadow-only boundary
14B targeted fallback semantics
3B combined gate/critic/evidence judge
bucket-specific primary proposer
disagreement-triggered second proposer
CodeIntel AST Evidence Graph
Memory / LanceDB scoring as selector input
Autoreason / DDTree pruning
Controlled Protocol
source_hash_guard
ast_locator
line-span / action_protocol
deterministic applier / rollback
Sandbox / Ultra Review
Claim Gate / Delivery Gate
Learning Closure / Meta-Opt
evidence context compression
verifier selector
```

### 7.3 Phase 1 / Phase 2 / Phase 3 建議

#### Phase 1：Preservation Audit

不要先改 code。先確認：

```text
目前 U3 scaffold 是否旁路 LocalModelPolicy、AG5、AB3、BD 優化？
```

輸出：

```text
PRESERVED / PARTIAL / LOST matrix
max 3 required fixes
no benchmark
no public claim
```

#### Phase 2：Executable LocalHeal U3 Correctness

目標不是效能，而是語義正確：

```text
Qwen candidate and DeepSeek candidate from identical clean baseline
persist both raw candidate outputs
persist both patch hashes
3B judge selection
reset/reconstruct baseline
apply selected candidate only
verifier
receipt proves selected_candidate_hash == applied_patch_hash
```

#### Phase 3：Reattach to 5 月 with_nexus Runner

把本地 U3 / memory / local portfolio 變成 with_nexus runner 的可選 backend / route profile：

```text
capability_ab_runner.py with_nexus path can select local heterogeneous backend
evidence bundle records model_uses_nexus=true
nexus_context_delivered=true
route_decision_present=true
committee trace present
memory trace present
codeintel trace present
claim gate present
```

#### Phase 4：Ceiling Eval

這時才測：

```text
3B judge + Qwen 7B + DeepSeek 6.7B + Nexus armor
```

是否能重現或超越 6 月 BD/AB3/AG5 的 local ceiling。

---

## 8. 建議給 Agent 的固定提示

後續可以貼給任何 agent：

```text
Context:
Nexus already had a proven May with_nexus execution route via scripts/bench/capability_ab_runner.py.
Do not claim Nexus lacks a main route.
The problem is that June local model / U3 / memory / patch protocol work did not stay attached to the May with_nexus capability A/B runner.

Goal:
Attach June local-model portfolio and U3 heterogeneous route back into the May with_nexus route, not into an isolated MEMORY-EVAL script.

Non-negotiable:
- No Qwen-only shortcut.
- No MEMORY-EVAL path as mainline.
- No manual receipt treated as runtime.
- No report-only success claim.
- No committee trace-only success claim.
- No public claim unless hidden verifier and claim gate pass.
- Preserve LocalModelPolicy v2.2, AG5 local portfolio optimization, AB3 full-route capability semantics, and BD ceiling follow-up constraints.

Must preserve:
- 3B gate + critic + evidence judge
- bucket-specific primary proposer
- disagreement-triggered second proposer
- Qwen 7B + DeepSeek 6.7B as local proposer portfolio
- targeted 14B fallback where resource-gated
- CodeIntel AST Evidence Graph
- Memory / LanceDB scoring
- DDTree / Autoreason pruning
- Controlled Protocol / source_hash_guard / ast_locator / action_protocol
- deterministic applier / rollback
- sandbox / ultra review
- claim / delivery gate
- learning closure

Current known gap:
U3 scaffold touches LocalHeal committee path, but has not proven reattachment to capability_ab_runner with_nexus route.
MEMORY-EVAL-9/11 are isolated Qwen 7B + MemoryRetrievalAdapter A/B diagnostics only.

First task:
Run preservation and route-alignment audit before implementation.
```

---

## 9. Current final verdict

目前最準確裁決：

```text
NEXUS_MAIN_ROUTE_EXISTED_IN_MAY
JUNE_LOCAL_OPTIMIZATIONS_ARE_REAL_BUT_FRAGMENTED
MEMORY_EVAL_IS_DIAGNOSTIC_NOT_MAINLINE
U3_PHASE_1_SCAFFOLD_IS_PARTIAL_AND_NOT_YET_MAIN_ROUTE
NEXT_STEP_IS_REATTACHMENT_TO_WITH_NEXUS_CAPABILITY_RUNNER
```

白話：

```text
5 月的 Nexus+Gemini 主路徑是真的。
6 月的本地模型優化也是真的。
但後來兩條線沒有接在一起。
現在要做的是把 6 月成果接回 5 月 with_nexus 主路徑，
而不是再用 MEMORY-EVAL 或 isolated LocalHeal script 代表 Nexus 全能力。
```
