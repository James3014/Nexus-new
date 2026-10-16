# N30R-W0 Closeout: Local Armor End-to-End Contract Audit

**Status**: N30R_W0_PARTIAL

## Classification
- CONTROL_PLANE_CONNECTED ✓
- PLANNER_TOPOLOGY_ONLY ✓
- PLANNER_EVIDENCE_BLIND ✓
- CAPABILITY_SELECTION_EMPTY ✓
- LOCKED_SEARCH_MISSING ✓
- VERIFIER_CONTRACT_CONNECTED ✓
- EVIDENCE_NOT_REACHING_PROMPT ✓

---

## 1. Worktree and environment
- path: /Users/jameschen/Workspace/nexus-n30r-real-core
- branch: fix/n30r-genuine-production-executor
- baseline SHA: 311c51047
- python: .venv/bin/python3 (3.14.0, uv managed)

## 2. Exact symbol map
- CapabilityPlanner.plan: nexus.engine.capability_planner.CapabilityPlanner.plan
- LocalModelExecutor.run: nexus.services.local_heal.local_model_executor.LocalModelExecutor.run
- LocalHealPipelineCapabilityExecutor.execute: nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute
- HealPipeline.run: nexus.services.local_heal.pipeline.HealPipeline.run
- InjectedLocalModelProvider.generate: nexus.services.local_heal.local_model_provider.InjectedLocalModelProvider.generate

## 3. Lane A — Planner Truth

| 項目 | 值 |
|------|-----|
| planner_version | capability_planner_v1 |
| selected_executor | local_model |
| execution_topology | localheal_pipeline |
| selected_capabilities | **[]** (空) |
| selected_capability_count | **0** |
| source visible to planner | NO (source_code 在 workspace 但未傳入 planner.plan()) |
| codeintel nonempty | NO (空 dict) |
| failure evidence visible | NO |
| protocol_mode | anchored_edit |

**結論: PLANNER_TOPOLOGY_ONLY** — Planner 只選了 topology，沒有選任何 capability。Planner 看不到 source code、看不到 codeintel、看不到 failure evidence。

## 4. Lane B — Binding Truth

### B0 (minimal)
- invoked: True
- pipeline_run_called: True
- pipeline_actual_execution: True
- provider_calls: 7

### B1 (armor binding)
- invoked: True
- pipeline_run_called: True
- pipeline_actual_execution: True
- source_anchor: True
- locked_search: False
- candidate_isolation_attempted: False
- provider_calls: 7

**Prompt delta B0 vs B1: false** — 兩者的 prompt 完全相同，因為 Planner 沒有選任何 capability，所以 B0 和 B1 的 selected_capabilities 差異沒有反映到 prompt。

## 5. Six-stage contract trace

| Stage | Captured | Source |
|-------|----------|--------|
| 1. Planner Input | ✓ | real CapabilityPlanner.plan() |
| 2. Planner Output | ✓ | real CapabilityPlanner.plan() return |
| 3. Executor Request | ✓ | LocalModelExecutor.run() spy |
| 4. Pipeline Context | ✓ | raw_model_metadata |
| 5. Model Prompt | ✓ | DeterministicMockProvider.generate() spy |
| 6. Receipt | ✓ | LocalModelExecutorResponse |

## 6. Capability Effect Ledger

所有 9 個稽核的 capability 都是:
- selected: false (Planner 沒選)
- invoked: false
- evidence_added: false
- prompt_delta: false
- outcome_contributed: false

**原因: Planner output `selected_capabilities` 為空，所以沒有任何 capability 被 bind 或 invoked。**

## 7. Contract Matrix

| Contract | Planner Input | Planner Output | Executor Request | Pipeline Context | Model Prompt | Receipt |
|----------|:---:|:---:|:---:|:---:|:---:|:---:|
| task statement | PRESENT | — | PRESENT | PRESENT | NO | hash |
| source code | PRESENT | — | filesystem | ? | NO | — |
| target file | PRESENT | — | PRESENT | PRESENT | NO | — |
| target symbol | PRESENT | — | PRESENT | PRESENT | NO | — |
| locked search | MISSING | — | MISSING | MISSING | NO | — |
| source anchor | — | — | derived | PRESENT (B1) | NO | — |
| verifier command | — | — | PRESENT | PRESENT | — | status |
| failure evidence | MISSING | — | MISSING | MISSING | NO | — |
| selected capabilities | — | **EMPTY** | EMPTY | EMPTY | — | — |
| memory evidence | — | — | MISSING | MISSING | NO | — |
| retry policy | — | snapshot | snapshot | — | — | — |
| candidate identity | — | — | — | — | — | hash |
| verifier result | — | — | — | — | — | status |

## 8. Candidate/apply/verifier workspace integrity
- target file: PRESENT (real workspace)
- source hash matches fixture: YES
- verifier same workspace: YES (verifier_command uses workspace path)
- candidate isolation attempted: NO (B1)

## 9. Confirmed wiring gaps

1. **Planner does not receive source code** — `source_code` 不在 `planner.plan()` 的 kwargs 中
2. **Planner does not receive codeintel** — `codeintel={}` 空 dict
3. **Planner does not receive failure evidence** — 沒有 failure context
4. **selected_capabilities is empty** — Planner 只選 topology，不選 capability
5. **locked_search not established** — 沒有 locked search 傳入 pipeline
6. **candidate_isolation_not_attempted** — pipeline 沒有嘗試 candidate isolation
7. **Evidence not reaching prompt** — 模型 prompt 中沒有任何 Nexus evidence

## 10. Confirmed working contracts
- CapabilityPlanner.plan() 可呼叫
- LocalModelExecutor.run() 可呼叫
- Pipeline topology (localheal_pipeline) 被正確解析
- Provider 被呼叫 (7 次)
- Source anchor 在 B1 中建立
- Verifier lifecycle 可走到 receipt

## 11. Unsupported assumptions
- ~~Nexus 對 7B 沒幫助~~ — 未測量
- ~~7B 容量不足~~ — 未測量
- ~~localheal_pipeline 太慢~~ — 未測量
- ~~Core 比 Bare 差~~ — 未測量

## 12. Next gate recommendation
**Status = N30R_W0_PARTIAL**

下一步: **Planner-to-Executor Evidence Contract Repair**

原因: Planner 輸出 `selected_capabilities=[]` 且看不到 source code。在修復 Planner 的 evidence input 之前，任何 benchmark 都只是測量「空 Armor」。

## 13. Claim boundary
- Nexus effectiveness not measured
- 7B capacity not measured
- Bare/Core uplift not measured
- No production readiness claim
- No public claim
