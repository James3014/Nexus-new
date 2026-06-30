# Nexus Policy Extraction Pack

**版本**：v1
**生成時間**：2026-06-15
**基準 Commit**：`fad8f32e`
**目的**：將 Nexus 的治理控制平面從 code-path 顯性化為完整的 agent policy plane

---

## A. Module Map：模組 → 所屬層級 → 輸入/輸出 → Authority

### Layer 1: Intake（問題進入治理）

| Module | 輸入 | 輸出 | Authority |
|--------|------|------|-----------|
| `autonomic_router.py` | task_description, repo_dir | ExecutionPlan (mode, confidence, matched_policies) | 可升級 L1→L2/L3；ExtensionGuard 強制 swarm |
| `budget_governor.py` | rounds, token_counts | TaskCompactionReceipt (compression_ratio, history_mode) | CRITICAL 時 drop history + force decomposition |
| `belief_engine.py` | assumption, evidence | confidence score [0.0, 1.0] | confidence < 0.5 觸發 warning |
| `context_hub.py` | task state, 19 layers | assembled context + audit_level decision | receipt gap → 強制 full audit |

### Layer 2: Deliberation（路由與推理決策）

| Module | 輸入 | 輸出 | Authority |
|--------|------|------|-----------|
| `capability_planner.py` | ExecutionPlan, capabilities | CapabilityPlan (decision_trace, budget) | 可 forbid/conditional capabilities；budget downgrade |
| `capability_registry.py` | name | metadata (phases, cost_weight, maturity) | 純 data，無 runtime decision |
| `s2t_strict.py` | candidates, risk_tier | S2TStrictDecision (selected, advisor_used) | 3B advisor 只在 low_risk+low_tier 可 override |
| `autonomy_observation.py` | execution data | LocalModelSuitabilityMatrix | 成功率 >80% + syntax >90% 才建議 local model |
| `cost_hook.py` | tool actions | cost prediction + budget check | BLOCKED if predicted > remaining |

### Layer 3: Execution（行動執行）

| Module | 輸入 | 輸出 | Authority |
|--------|------|------|-----------|
| `capability_gate.py` | phase, tools | whitelist (available/hidden tools) | 每 phase 只暴露允許的 tools |
| `repair_loop_service.py` | task, skill, state | success/failure | Max 3 attempts；attempt 2 覦發 battle_swarm |
| `repair_attempt_service.py` | task, state, attempt | attempt_result | LeWMPredictor 可 REJECT 以 abort |
| `patch_synthesis.py` | localized_files, plan | patch (SEARCH/REPLACE) | Syntax gate 驗證 |
| `evaluation_gate.py` | repro_script | TestResult list + redacted report | hidden verifier required but not configured → FAIL |

### Layer 4: Claim（宣稱與驗證）

| Module | 輸入 | 輸出 | Authority |
|--------|------|------|-----------|
| `critique_engine.py` | agent output | PASS / BLOCKED | overclaim + anti-rationalization + hallucination score |
| `hallucination_guard.py` | claim, evidence | score [0-10], status (VERIFIED/PARTIAL/REJECTED) | strict quarantine mode: PARTIAL = REJECTED |
| `capability_receipts.py` | CapabilityPlan | CapabilityReceipt list | public_claim_safe 判定 |
| `capability_receipt_policy.py` | receipt | route_quality_actionable | selected_to_invoked ≥70%, invoked_to_evidence ≥95% |
| `delivery/gate.py` | task_level | CompletionResult | DOC=1 cmd, SMALL_FIX=1, FEATURE=2, DELIVERY=2+1 artifact |
| `delivery/contract.py` | task_level | DeliveryContract | hard floors for min_verification_commands |

### Layer 5: Learning（學習與寫回）

| Module | 輸入 | 輸出 | Authority |
|--------|------|------|-----------|
| `attempt_settlement_service.py` | attempt_result | success/writeback_pending/retry | auto-evidence 寫入 hallucination_evidence.json |
| `policy_drift.py` | paths, policies | drift_detected boolean | physical gate + semantic gate + path drift |
| `drift_stop_gate.py` | manifest_hash, receipt_hash | alignment verified / drift detected | old_policy must equal new_policy for promotion |
| `skill_lifecycle.py` | usage event | L0→L3 promotion | scan gate + usage threshold |
| `context_compactor.py` | state, confidence | verified_facts summary | dedup by outcome string |

---

## B. Decision Points：每個 Gate / Policy Check / Fallback / Abort / Promotion

### Intake Decision Points

| ID | 觸發條件 | 決策 | 降級路徑 | Receipt |
|----|----------|------|----------|---------|
| DP-01 | autonomic_router 收到 task | mode = standard \| swarm \| research_first | ExtensionGuard: code-touching → swarm | ExecutionPlan |
| DP-02 | HazardMapper: red-zone module | forced upgrade L1→L3 | — | ExecutionPlan.reason |
| DP-03 | MFP: low confidence | forced upgrade to L2/L3 | — | ExecutionPlan.reason |
| DP-04 | GemmaGuard: outlier score | reject classifier output | fallback to rule-based | ExecutionPlan.reason |
| DP-05 | budget_governor: CRITICAL | drop history + disable research + force decomposition | — | TaskCompactionReceipt |
| DP-06 | belief_engine: confidence < 0.5 | inject belief_warning into context | — | belief_update record |

### Deliberation Decision Points

| ID | 觸發條件 | 決策 | 降級路徑 | Receipt |
|----|----------|------|----------|---------|
| DP-07 | capability_planner: budget exceeded | downgrade conditional capabilities | safety floor protection | CapabilityPlan |
| DP-08 | s2t_strict: candidate selection | 3B advisor selects (low_risk only) | abstain on parse failure | S2TStrictDecision |
| DP-09 | s2t_strict: semantic safety gate | advisor must select candidate that exists + passes verifier + has evidence | trust mismatch → reject | S2TStrictDecision |
| DP-10 | autonomy_observation: suitability | local model recommended if success >80% + syntax >90% | trust mismatch = "high" | LocalModelSuitabilityMatrix |
| DP-11 | cost_hook: predicted > remaining | BLOCKED | — | cost prediction |
| DP-12 | cost_hook: >70% remaining | WARN_OPTIMIZE | — | cost prediction |

### Execution Decision Points

| ID | 觸發條件 | 決策 | 降級路徑 | Receipt |
|----|----------|------|----------|---------|
| DP-13 | capability_gate: phase transition | whitelist tools for phase | hidden tools not accessible | tools_json |
| DP-14 | repair_loop: attempt 2 | trigger battle_swarm (4 workers) | — | battle_result |
| DP-15 | repair_attempt: LeWM REJECTED | abort task | — | lewm_sim_status |
| DP-16 | patch_synthesis: syntax gate | apply patch or reject | — | patch_decision |
| DP-17 | evaluation_gate: hidden verifier not configured | FAIL | — | TestResult |
| DP-18 | evaluation_gate: all tests pass | PASS | — | redacted report |

### Claim Decision Points

| ID | 觸發條件 | 決策 | 降級路徑 | Receipt |
|----|----------|------|----------|---------|
| DP-19 | critique_engine: overclaim detected | BLOCKED (RationalizationError) | — | hallucination note |
| DP-20 | critique_engine: anti-rationalization | BLOCKED (blacklisted phrases) | — | hallucination note |
| DP-21 | critique_engine: hallucination score > 5 | BLOCKED | — | hallucination note |
| DP-22 | hallucination_guard: score threshold | VERIFIED / PARTIAL / REJECTED | strict quarantine: PARTIAL=REJECTED | analysis dict |
| DP-23 | capability_receipt_policy: quality check | selected_to_invoked ≥70% | route_quality_actionable | coverage report |
| DP-24 | delivery_gate: task_level | DOC=1, SMALL_FIX=1, FEATURE=2, DELIVERY=2+1 | live delivery requires human approval | CompletionResult |

### Learning Decision Points

| ID | 觸發條件 | 決策 | 降級路徑 | Receipt |
|----|----------|------|----------|---------|
| DP-25 | attempt_settlement: passed | COMMIT | writeback_pending → audit_rollback | auto-evidence JSON |
| DP-26 | attempt_settlement: failed | audit_rollback + retry | — | auto-evidence JSON |
| DP-27 | policy_drift: path drift detected | BLOCKED | — | drift report |
| DP-28 | drift_stop_gate: hash mismatch | BLOCKED | — | drift report |
| DP-29 | skill_lifecycle: usage threshold met | promote L0→L1→L2→L3 | scan gate | skill metadata |
| DP-30 | context_compactor: new verified fact | crystallize to summary | dedup check | verified_facts |

---

## C. Receipt Schemas：每種 Receipt 的欄位、來源、校驗、Claim Impact

### C1. ExecutionPlan（Intake）

```json
{
  "mode": "standard | swarm | research_first",
  "reason": "string — upgrade reason if forced",
  "confidence": "float [0,1]",
  "matched_policies": ["policy_id: ..."],
  "anchor_stem": "4-char anchor"
}
```
- **來源**: `autonomic_router.py`
- **校驗**: mode ∈ {standard, swarm, research_first}
- **Claim Impact**: mode 決定後續所有 execution path

### C2. TaskCompactionReceipt（Budget）

```json
{
  "compression_ratio": "float",
  "history_mode": "full | summarize | drop",
  "research_mode": "full | targeted | disabled",
  "max_rounds_delta": "int",
  "compaction_reason_codes": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
}
```
- **來源**: `budget_governor.py`
- **校驗**: history_mode ∈ {full, summarize, drop}
- **Claim Impact**: CRITICAL 時 context 被大幅壓縮

### C3. CapabilityPlan（Deliberation）

```json
{
  "decision_trace": "list — capability selection reasons",
  "replan_trace": "list — budget downgrade history",
  "signal_snapshot": "dict — input signals",
  "ssd_route_map": "dict — selected-to-state mapping",
  "context_slimming_policy": "dict — per-phase token budgets",
  "skill_mount_evidence": "list — skill injection records",
  "research_isolation": "dict — research boundary",
  "s2t_shadow_score": "float — 3B advisor score"
}
```
- **來源**: `capability_planner.py`
- **校驗**: decision_trace 非空；mempalace_gate + artifact_gate + claim_gate ∈ required
- **Claim Impact**: 驅動後續所有 capability receipt

### C4. S2TStrictDecision（Routing）

```json
{
  "passed": "bool",
  "selected_candidate_id": "string",
  "reason_codes": ["list — trust_mismatch, semantic_rejected, etc."],
  "advisor_used": "bool",
  "advisor_outcome_status": "string",
  "advisor_model": "string",
  "advisor_provenance_hash": "SHA256 string"
}
```
- **來源**: `s2t_strict.py`
- **校驗**: advisor_provenance_hash 必須 match registered adapter
- **Claim Impact**: routing 決定整個 execution path

### C5. HallucinationAnalysis（Claim）

```json
{
  "score": "int [0-10]",
  "status": "VERIFIED | PARTIAL | REJECTED",
  "triggers": ["list — trigger rule names"],
  "trigger_details": {"rule_name": "detail"},
  "verdict": "PASS | BLOCKED",
  "force_rejected": "bool"
}
```
- **來源**: `hallucination_guard.py`
- **校驗**: score ≤ threshold; strict quarantine: PARTIAL = REJECTED
- **Claim Impact**: BLOCKED 直接阻止 delivery

### C6. CapabilityReceipt（Claim）

```json
{
  "capability_id": "string",
  "selected": "bool",
  "invoked": "bool",
  "evidence_present": "bool",
  "outcome_contributed": "bool",
  "public_claim_safe": "bool",
  "failure_reason": "string | null"
}
```
- **來源**: `capability_receipts.py`
- **校驗**: failure_reason ∈ {selected_without_injection, used_without_evidence, pending_executor}
- **Claim Impact**: public_claim_safe 決定是否可對外宣稱

### C7. AutoEvidence（Settlement）

```json
{
  "code_artifacts": ["list — files modified"],
  "test_artifacts": ["list — test results"],
  "command_artifacts": ["list — commands executed"],
  "aggregates": {"pass_rate": "float", "total_tests": "int"},
  "task_id": "string",
  "timestamp": "ISO8601"
}
```
- **來源**: `attempt_settlement_service.py`
- **校驗**: 寫入 `.nexus/reports/hallucination_evidence.json`（agent-tamper-proof）
- **Claim Impact**: 唯一被視為 "tamper-proof" 的 evidence

### C8. DeliveryCompletionResult（Delivery）

```json
{
  "status": "IMPLEMENTED | PARTIALLY_VERIFIED | VERIFIED | DELIVERY_READY",
  "verification_records": ["list — test results"],
  "policy_failures": ["list — failed policies"],
  "task_level": "DOC | SMALL_FIX | FEATURE | DELIVERY"
}
```
- **來源**: `delivery/gate.py`
- **校驗**: task_level 對應 min_verification_commands + required_artifacts
- **Claim Impact**: DELIVERY_READY 需要 human approval

---

## D. Failure Taxonomy：錯誤碼、阻斷點、回退方式、是否可重試

### D1. Routing Failures

| 錯誤碼 | 來源 | 觸發條件 | 阻斷點 | 回退方式 | 可重試 |
|--------|------|----------|--------|----------|--------|
| `TRUST_MISMATCH` | s2t_strict | verifier_result != pass | routing gate | reject advisor decision | Yes |
| `SEMANTIC_REJECTED` | s2t_strict | advisor selected non-existent candidate | routing gate | abstain | Yes |
| `ADVISOR_PARSE_FAILURE` | s2t_strict | 3B output parse error | routing gate | use baseline selector | Yes |
| `GEMMA_OUTLIER` | autonomic_router | classifier score outlier | intake | fallback to rule-based | Yes |
| `EXTENSION_GUARD_UPGRADE` | autonomic_router | code-touching task | intake | force swarm mode | N/A (forced) |

### D2. Execution Failures

| 錯誤碼 | 來源 | 觸發條件 | 阻斷點 | 回退方式 | 可重試 |
|--------|------|----------|--------|----------|--------|
| `SEARCH_MISMATCH` | patch_synthesis | SEARCH block doesn't match source | patch phase | retry with fuzzy anchor | Yes |
| `SYNTAX_INVALID` | patch_applier | patch fails syntax gate | patch phase | retry with different approach | Yes |
| `MODEL_EMPTY_RESPONSE` | llm_client | model returns empty | patch phase | retry with different model | Yes |
| `REFUSAL_DETECTED` | model_result | model refuses to patch | patch phase | retry with rephrased prompt | Yes |
| `NO_LLM_CLIENT` | patch_synthesis | no model available | patch phase | abort | No |
| `VERIFICATION_FAILED` | evaluation_gate | tests fail after patch | verification | retry repair loop | Yes (max 3) |
| `LEWM_REJECTED` | repair_attempt | cost prediction too high | execution | abort | No |
| `LOCALIZATION_NO_FILES` | localization | no relevant files found | localization | retry with broader search | Yes |
| `LOCALIZATION_EMPTY` | localization | budget enforcement leaves nothing | localization | retry | Yes |
| `BUDGET_EXCEEDED` | cost_hook | predicted cost > remaining | pre-execution | BLOCKED | No |

### D3. Claim Failures

| 錯誤碼 | 來源 | 觸發條件 | 阻斷點 | 回退方式 | 可重試 |
|--------|------|----------|--------|----------|--------|
| `OVERCLAIM_DETECTED` | critique_engine | restricted words without evidence | claim review | BLOCKED | No |
| `ANTI_RATIONALIZATION` | critique_engine | blacklisted phrases (skip tests, manual check) | claim review | BLOCKED | No |
| `HALLUCINATION_HIGH` | critique_engine | hallucination score > 5 | claim review | BLOCKED | No |
| `HALLUCINATION_REJECTED` | hallucination_guard | score exceeds threshold | claim review | BLOCKED | No |
| `HALLUCINATION_PARTIAL` | hallucination_guard | score borderline | claim review | PARTIAL (quarantine: REJECTED) | No |
| `EVIDENCE_WITHOUT_GATE` | context_hub | evidence exists but gate not passed | context assembly | force full audit | Yes |
| `SELECTED_WITHOUT_INVOCATION` | capability_receipts | capability selected but not invoked | receipt check | route_quality_actionable = False | Yes |

### D4. Delivery Failures

| 錯誤碼 | 來源 | 觸發條件 | 阻斷點 | 回退方式 | 可重試 |
|--------|------|----------|--------|----------|--------|
| `DELIVERY_REQUIRES_HUMAN` | delivery/gate | live delivery | delivery gate | block until human approval | No |
| `CONTENT_QUALITY_FAIL` | delivery/gate | .md artifact quality | delivery gate | retry edit | Yes |
| `MIN_VERIFICATION_NOT_MET` | delivery/contract | insufficient test commands | delivery gate | add more verification | Yes |
| `COMMITTEE_COVERAGE_FAILURE` | capability_receipt_policy | selected_to_invoked < 70% | receipt check | BLOCKED | No |

### D5. Learning Failures

| 錯誤碼 | 來源 | 觸發條件 | 阻斷點 | 回退方式 | 可重試 |
|--------|------|----------|--------|----------|--------|
| `POLICY_DRIFT` | policy_drift | path or semantic drift | learning gate | BLOCKED | No |
| `DRIFT_STOP_GATE` | drift_stop_gate | manifest hash mismatch | promotion gate | BLOCKED | No |
| `WRITEBACK_PENDING` | attempt_settlement | code done but writeback needed | settlement | audit_rollback | Yes |

---

## E. Implicit Policy Debt：靠 Prompt / 人工默契 / Hardcoded String 的規則

### E1. Prompt-Dependent Rules（未 codified 到 schema）

| 規則 | 目前位置 | 觸發方式 | 風險 |
|------|----------|----------|------|
| "何時該搜尋" | planner prompt (LLM 生成) | LLM 判斷 | 模型可能不搜尋或過度搜尋 |
| "何時該 abstain" | s2t_strict.py: advisor parse failure | string match "abstain" | 未 codified 為 enum |
| "何時可以 overrule selector" | 3B advisor low_risk only | env var control | 規則在 prompt 裡，不在 schema 裡 |
| "什麼叫可 public claim" | capability_receipt_policy.py | PUBLIC_CLAIM_CAPABILITIES list | list 是 hardcoded，不動態 |
| "什麼樣的 patch 算 evidence complete" | capability_receipts.py | evidence_present bool | 邏輯散在多個 adapter 裡 |
| "何時該 stop-and-escalate" | budget_governor.py CRITICAL | pressure level 閾值 | 閾值 hardcoded，不動態調整 |
| "何時該 deterministic rescue" | planning.py FAST_MODE | NEXUS_FAST_MODE env var | 規則在 env var，不在 policy schema |

### E2. Hardcoded String Matching（脆弱的 governance）

| 位置 | Hardcoded String | 風險 |
|------|------------------|------|
| `critique_engine.py` | restricted_words = {"solved", "fixed", "verified", "100%", ...} | 語言變化時失效 |
| `critique_engine.py` | blacklist = {"skip tests", "manual check", "do later", ...} | 語言變化時失效 |
| `s2t_strict.py` | "trust_mismatch" string | 字串比對，非 enum |
| `capability_receipts.py` | failure_reason = "selected_without_injection" | 字串常量，易 typo |
| `hallucination_guard.py` | trigger rule names from JSON schema | 依賴 schema 文件存在 |
| `policy_drift.py` | AGENTS.md allowed/forbidden patterns | 正則 pattern 硬編碼 |

### E3. Missing Schema / Missing Tests / Missing Rollback Drill

| 政策點 | Schema 存在 | Tests 存在 | Rollback Drill | 風險等級 |
|--------|-------------|------------|----------------|----------|
| S2T routing receipt | ✅ | ✅ | ❌ | High — routing failure 無 drill |
| Hallucination guard verdict | ✅ | ✅ | ❌ | Medium — score threshold 未經 drill |
| Capability receipt coverage | ✅ | ✅ | ❌ | Medium — 低覆蓋率無 rollback path |
| Budget governor CRITICAL | Partial | ✅ | ❌ | High — context drop 無 rollback |
| Policy drift detection | ✅ | ❌ | ❌ | High — drift 無 test coverage |
| Delivery gate human approval | Partial | ❌ | ❌ | High — human gate 無 fallback |
| 3B advisor provenance lock | ✅ | ✅ | ❌ | Medium — hash mismatch 無 drill |
| BattleSwarm cross-branch | ❌ | ❌ | ❌ | High — 完全無 schema + 無 test |
| Failure memory injection | ❌ | ❌ | ❌ | Medium — retry 不注入 failure context |
| Skill memory query layer | ❌ | ❌ | ❌ | Medium — skill routing 無 history query |

---

## F. Policy Source of Truth Table

| Policy ID | Owner Module | File | Runtime Stage | Hard/Soft | Deterministic/Model | Evidence Required | Rollback Path |
|-----------|--------------|------|---------------|-----------|---------------------|-------------------|---------------|
| P-ROUTE-01 | autonomic_router | autonomic_router.py | Intake | Hard | Deterministic | ExecutionPlan | mode fallback |
| P-ROUTE-02 | hazard_mapper | autonomic_router.py | Intake | Hard | Deterministic | ExecutionPlan | forced upgrade |
| P-ROUTE-03 | mfp_guard | autonomic_router.py | Intake | Hard | Deterministic | ExecutionPlan | forced upgrade |
| P-ROUTE-04 | gemma_guard | autonomic_router.py | Intake | Hard | Deterministic | ExecutionPlan | rule-based fallback |
| P-BUDGET-01 | budget_governor | budget_governor.py | Deliberation | Hard | Deterministic | TaskCompactionReceipt | N/A (forced) |
| P-PLAN-01 | capability_planner | capability_planner.py | Deliberation | Hard | Model-Assisted | CapabilityPlan | budget downgrade |
| P-PLAN-02 | capability_planner | capability_planner.py | Deliberation | Hard | Deterministic | CapabilityPlan | safety floor |
| P-PLAN-03 | capability_planner | capability_planner.py | Deliberation | Hard | Deterministic | CapabilityPlan | conditional → forbidden |
| P-S2T-01 | s2t_strict | s2t_strict.py | Routing | Hard | Model-Assisted | S2TStrictDecision | baseline selector |
| P-S2T-02 | s2t_strict | s2t_strict.py | Routing | Hard | Deterministic | S2TStrictDecision | semantic gate |
| P-S2T-03 | s2t_strict | s2t_strict.py | Routing | Soft | Model-Assisted | S2TStrictDecision | 3B advisor (low_risk only) |
| P-COST-01 | cost_hook | cost_hook.py | Pre-Execution | Hard | Deterministic | cost prediction | BLOCKED |
| P-COST-02 | cost_hook | cost_hook.py | Pre-Execution | Soft | Deterministic | cost prediction | WARN_OPTIMIZE |
| P-GATE-01 | capability_gate | capability_gate.py | Execution | Hard | Deterministic | tools_json | N/A (phase-based) |
| P-GATE-02 | evaluation_gate | evaluation_gate.py | Verification | Hard | Deterministic | TestResult | BLOCKED |
| P-GATE-03 | evaluation_gate | evaluation_gate.py | Verification | Hard | Deterministic | TestResult | FAIL (no verifier) |
| P-CLAIM-01 | critique_engine | critique_engine.py | Claim | Hard | Model-Assisted | hallucination note | BLOCKED |
| P-CLAIM-02 | critique_engine | critique_engine.py | Claim | Hard | Deterministic | hallucination note | BLOCKED |
| P-CLAIM-03 | hallucination_guard | hallucination_guard.py | Claim | Hard | Deterministic | analysis dict | REJECTED |
| P-CLAIM-04 | capability_receipt_policy | capability_receipt_policy.py | Claim | Hard | Deterministic | coverage report | route_quality_actionable |
| P-DELIVERY-01 | delivery_gate | delivery/gate.py | Delivery | Hard | Deterministic | CompletionResult | human approval |
| P-DELIVERY-02 | delivery_contract | delivery/contract.py | Delivery | Hard | Deterministic | DeliveryContract | add verification |
| P-LEARN-01 | policy_drift | policy_drift.py | Learning | Hard | Deterministic | drift report | BLOCKED |
| P-LEARN-02 | drift_stop_gate | drift_stop_gate.py | Learning | Hard | Deterministic | drift report | BLOCKED |
| P-LEARN-03 | skill_lifecycle | skill_lifecycle.py | Learning | Soft | Deterministic | skill metadata | scan gate |
| P-AUTO-01 | autonomy_observation | autonomy_observation.py | Observation | Soft | Model-Assisted | AutonomyObservationReceipt | trust mismatch = high |
| P-BELIEF-01 | belief_engine | belief_engine.py | Context | Soft | Deterministic | belief_update | belief_warning |
| P-CTX-01 | context_hub | context_hub.py | Context | Hard | Model-Assisted | context_assembly_contract | force full audit |
| P-CTX-02 | context_compactor | context_compactor.py | Context | Soft | Deterministic | verified_facts | dedup |
| P-SETTLE-01 | attempt_settlement | attempt_settlement_service.py | Settlement | Hard | Deterministic | auto-evidence JSON | audit_rollback |
| P-SETTLE-02 | attempt_settlement | attempt_settlement_service.py | Settlement | Hard | Deterministic | auto-evidence JSON | retry (max 3) |

---

## G. Five-Layer Policy Plane Mapping

### G1. Intake Policy（問題分類為治理對象）

**現有實現**：
- `autonomic_router.py`: mode selection + hazard/mfp/gemma guards
- `budget_governor.py`: pressure level → compaction strategy
- `belief_engine.py`: confidence scoring → warning injection

**未成文規則**：
- 何時該升級到 swarm（ExtensionGuard: code-touching）
- 何時該 research_first（MFP: low confidence）
- 何時該 abort（LeWM REJECTED）

### G2. Deliberation Policy（路由與推理受約束）

**現有實現**：
- `capability_planner.py`: capability selection + budget downgrade
- `s2t_strict.py`: fail-closed routing with 3B advisor
- `cost_hook.py`: token budget prediction + interception

**未成文規則**：
- 3B advisor 何時可以 override（only low_risk + low_tier）
- 預算不足時哪些 capabilities 可以降級（safety floor protection）
- 何時該 research isolation vs full research

### G3. Execution Policy（行動邊界）

**現有實現**：
- `capability_gate.py`: phase-based tool whitelist
- `repair_loop_service.py`: max 3 attempts + battle_swarm
- `patch_synthesis.py`: SEARCH/REPLACE protocol + syntax gate

**未成文規則**：
- 何時該 deterministic rescue（FAST_MODE）
- 何時該 stop-and-escalate（budget CRITICAL）
- BattleSwarm 的 4 個 worker 何時共享 discovery

### G4. Claim Policy（宣稱可信度）

**現有實現**：
- `critique_engine.py`: overclaim + anti-rationalization + hallucination
- `hallucination_guard.py`: schema-driven scoring
- `capability_receipt_policy.py`: public_claim_safe 判定

**未成文規則**：
- 什麼詞需要 HIGH confidence evidence bundle
- 什麼只能說 tentative
- 什麼叫 evidence complete（散在多個 adapter 裡）

### G5. Learning Policy（學習邊界）

**現有實現**：
- `policy_drift.py`: dual-gate verifier + path drift
- `drift_stop_gate.py`: manifest hash alignment
- `skill_lifecycle.py`: L0→L3 promotion

**未成文規則**：
- 哪些軌跡可進 S2T training（3B 只能 shadow，不能採納）
- 哪些必須 redact
- 哪些不能作為正樣本

---

*報告基準：2026-06-15，基於 Nexus 當前代碼（commit fad8f32e）*
*模組數量：22 primary governance modules + 17 receipt modules + 27 contract modules + 30 gate modules*
