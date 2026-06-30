# Nexus Route Audit: 3B Judge + Qwen 7B + DeepSeek 6.7B + Nexus Armor

**Date**: 2026-06-22  
**Scope**: Read-only audit of runtime wiring vs. historical artifacts  
**Verdict**: HISTORICAL/MANUAL ONLY — current runtime disconnected

---

## A. May Gemini Bare Claim

**Which file proves Nexus+Gemini beat Gemini bare?**

| File | Line | Claim |
|------|------|-------|
| `docs/reports/NEXUS_PUBLICATION_READY_12X2_SUMMARY_2026-05-20.md` | L9 | Gemini+Nexus 24/24 (100%) vs Gemini bare 16/24 (66.7%) |
| `docs/reports/GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-05-01.md` | L19, L88 | Gemini bare vs Gemini+Nexus metric tables |
| `docs/reports/GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-04-28.md` | L19, L60 | Gemini+Nexus 3/3 vs Gemini bare 0/3 smoke test |

**Exact metric**: 24/24 verified delivery (100%) vs 16/24 (66.7%), wall-time 0.92s/row vs 39.3s/row.  
**Task count**: 12 tasks x 2 runs = 24 task-arm pairs.  
**Date/report**: 2026-05-20, `NEXUS_PUBLICATION_READY_12X2_SUMMARY_2026-05-20.md`.  
**Runtime evidence or report-only?**: **Report-only.** The report contains static metric tables. No `artifacts/runtime/` execution trace was found for these specific Gemini-only benchmarks. The benchmarks used cloud Gemini API calls, not local_heal runtime.

---

## B. Historical Local Heterogeneous Evidence

**Files proving 3B judge + Qwen 7B + DeepSeek 6.7B existed:**

| File | Route IDs | Key Content |
|------|-----------|-------------|
| `docs/reports/v3_heterogeneous_route_promotion_readiness_decision_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | "核心模型組: qwen2.5-coder:3b (Judge) + qwen2.5-coder:7b (Primary) + deepseek-coder:6.7b (Secondary)" |
| `docs/reports/t2_heterogeneous_experimental_route_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | Dual proposer config |
| `docs/reports/t3_expanded_heterogeneous_route_benchmark_v0.md` | `qwen_7b_plus_deepseek_6_7b_dual_proposer` | Route B: 100% (4/4) repair rate |
| `docs/reports/u3_expanded_heterogeneous_route_benchmark_v0.md` | `qwen_7b_plus_deepseek_6_7b_dual_proposer` | Route B: 100% (8/8) |
| `docs/reports/r6_heterogeneous_shadow_benchmark_v0.md` | `qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b` | 100% (6/6) repair rate |

**Route IDs found in artifacts:**
- `local_heterogeneous_portfolio_experimental_v0` (19 artifact matches)
- `local_heterogeneous_portfolio_shadow_v0`
- `qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b` (88 artifact matches)
- `qwen_7b_plus_deepseek_6_7b_dual_proposer` (173 artifact matches)

**Are receipts say manual_only_experimental / manual_invocation_only?**  
**No exact matches found** for either string in any file. However, the route contracts in artifacts show:
- `artifacts/runtime/u1_heterogeneous_route_hardening_v0/route_invocation_contract.json` — contains CLI flag `--route local_heterogeneous_portfolio_experimental_v0`
- `artifacts/runtime/t2_heterogeneous_experimental_route_v0/route_contract.json` — config_override pattern
- These are **manual CLI invocations**, not automatic runtime routing

**Metrics**: 100% repair rate across 6-12 tasks per benchmark. Verifier results present. But all from standalone benchmark scripts, not from integrated `HealOrchestrator.run()`.

---

## C. Current Runtime Wiring

| Item | YES/NO/PARTIAL | Evidence |
|------|----------------|----------|
| **DeepSeek 6.7B allowed in backend resource policy** | **NO** | `backend_resource_policy.py:48-94` — DEFAULT_POLICIES contains only: `qwen2.5:3b`, `qwen2.5-coder:7b`, `gemma4-coder-12b-q4km:latest`, `deepseek-r1-14b-q4km:latest` (FORBIDDEN), `gpt-4o`, `claude-3-5-sonnet`. **`deepseek-coder:6.7b-instruct` is NOT listed.** |
| **3B judge role contract exists** | **PARTIAL** | `role_contract.py:9` defines `SELECTOR = "selector"` with comment "3B: candidate selection, reranking, budget policy". `_model_name_to_role()` at L68 maps any model with "3b" in name to SELECTOR. But no model is explicitly named "judge" — the role is SELECTOR, not JUDGE. |
| **Qwen 7B proposer role exists** | **NO** | `role_contract.py` defines `SEARCHER = "searcher"` for 7B models (L10), but there is **no PROPOSER role**. The pipeline is SELECTOR/SEARCHER/PATCHER/GOVERNANCE. No "proposer" concept in runtime code. |
| **DeepSeek secondary proposer role exists** | **NO** | No `secondary_proposer`, `second_proposer`, or `proposer` role exists anywhere in `local_heal/` runtime code. Zero grep matches for `proposer` as a role name. |
| **Dual proposer route exists as executable route** | **NO** | `native_route_adapter.py` defines single-model route decisions per phase (3b/7b/12b tiers). No dual-model, multi-proposer, or heterogeneous routing logic. `CommitteeOrchestrator` does multi-sample but uses the **same** patch_phase model (14B/7B mix), not independent 7B+6.7B proposers. |
| **3B judge actually invoked** | **PARTIAL** | `reasoning_advisory_bridge.py:29` passes `judge_count=3` to `AutoreasonService().run()` — this is an advisory/reasoning module, not the route-selection judge. The 3B model can be selected via `_model_name_to_role()` if named with "3b", but no code invokes it as a "judge" for dual-proposer candidate selection. |
| **Two candidate outputs persisted** | **NO** | `committee_orchestrator.py:39-49` collects multiple proposals but from the **same** `patch_phase.execute(ctx)` call, not from two independent proposers. No dual-model candidate persistence found. |
| **Judge selection persisted** | **NO** | `evidence_harness.py:30` has `judge_output: str = ""` field — always empty string in observed artifacts (`rrl3_runs/C_*/evidence_bundle.json` shows `"judge_output": ""`). |
| **Selected candidate applied** | **NO** | Standard single-patch flow in `orchestrator.py` — one `final_patch` per run. No dual-candidate selection → application path. |
| **Verifier executed** | **YES** | `micro_verifier.py` (full file), `evaluation_gate.py:33-69` `run_hidden_verifier()`, `phases/verification.py` — verifier is deeply wired. |
| **Nexus armor gates/capabilities invoked** | **YES** | `targeted_fallback.py:21-29` `armor_active` parameter, `governance_gate.py`, `claim_delivery_gate.py`, `evidence_harness.py` — full armor stack. |
| **Learning Closure written** | **YES** | `learning_closure_bridge.py:512-524` called from `orchestrator.py:512-524` via `_write_learning_closure()`. Writes to `.nexus/` store. |

---

## D. MEMORY-EVAL-9 / 11 Reality

| Question | Answer |
|----------|--------|
| **Which models are actually called?** | **Qwen 2.5 Coder 7B only.** Both scripts (`run_memory_eval_9_real_model_ab.py:44-51`, `run_memory_eval_11_c13453_real_model_ab.py:41-50`) verify Ollama has `qwen2.5-coder:7b` and use it exclusively. |
| **Is it Qwen-only memory A/B?** | **YES.** Both evals test MemoryRetrievalAdapter on/off with the **same single Qwen 7B model**. No 3B judge, no DeepSeek proposer, no dual-model comparison. |
| **Is it full Nexus armor or isolated eval script?** | **Isolated eval script.** Both scripts instantiate `HealOrchestrator(phases=[], governance_gate=GovernanceGate())` — empty phases, no real pipeline. They call `orchestrator.run(ctx)` but with pre-populated `final_patch` and `patch_applied=True`, so the orchestrator just writes artifacts without running real repair phases. No verifier execution (EVAL-9 sets `solve_eligible=False` explicitly; EVAL-11 checks verifier output files that may not exist). |

---

## E. Gap Verdict

**3. historical/manual only, current runtime disconnected**

The route "3B judge + Qwen 7B + DeepSeek 6.7B + Nexus armor" exists exclusively in:
- Historical benchmark reports (`docs/reports/t2_*, t3_*, u3_*, r6_*`)
- Historical benchmark artifacts (`artifacts/runtime/t2_*, t3_*, u3_*, r6_*`)
- Manual CLI invocation contracts (`artifacts/runtime/*/route_contract.json`)

**Zero runtime wiring** connects these components in the actual `HealOrchestrator` / `NativeRouteAdapter` / `BackendResourcePolicy` / `RoleContract` code. The runtime has:
- No `deepseek-coder:6.7b-instruct` in resource policy
- No "proposer" or "judge" role (only SELECTOR/SEARCHER/PATCHER/GOVERNANCE)
- No dual-candidate selection or comparison logic
- No heterogeneous model routing

---

## F. Implementation Plan

### Minimal files to touch (max 10):

| # | File | Change |
|---|------|--------|
| 1 | `nexus/services/local_heal/backend_resource_policy.py` | Add `deepseek-coder:6.7b-instruct` to `DEFAULT_POLICIES` with `LOCAL_7B` tier, `ALLOWED` policy |
| 2 | `nexus/services/local_heal/role_contract.py` | Add `PROPOSER` role to `ModelRole`, `JUDGE` alias for SELECTOR, update `_model_name_to_role()` to recognize deepseek-coder |
| 3 | `nexus/services/local_heal/native_route_adapter.py` | Add `dual_proposer` route type in `ROUTE_RULES`, wire 7b+6.7b dual-path in `decide()` |
| 4 | `nexus/services/local_heal/candidate_generation.py` | Add `DualProposerCandidateGenerator` that runs Qwen 7B and DeepSeek 6.7B independently |
| 5 | `nexus/services/local_heal/orchestrator.py` | Wire dual-candidate selection → judge → selected-candidate-apply flow after `patch_phase` |
| 6 | `nexus/services/local_heal/evidence_harness.py` | Populate `judge_output` field (currently hardcoded empty) |
| 7 | `nexus/services/local_heal/llm_client.py` | Ensure model name routing supports both qwen2.5-coder:7b and deepseek-coder:6.7b-instruct via Ollama |
| 8 | `nexus/services/local_heal/committee_orchestrator.py` | Refactor to use independent proposers instead of same-model multi-sample |
| 9 | `nexus/services/local_heal/evaluation_gate.py` | Wire hidden verifier to run on each candidate independently |
| 10 | `nexus/services/local_heal/learning_closure_bridge.py` | Ensure closure captures dual-proposer route metadata |

### Acceptance gates:

1. `deepseek-coder:6.7b-instruct` appears in `BackendResourcePolicy().list_allowed_models()`
2. `RoleContract` maps deepseek-coder models to a proposer/searcher role
3. `NativeRouteAdapter.decide()` returns `dual_proposer` route_id for appropriate inputs
4. `HealOrchestrator.run()` persists two candidate outputs when dual mode active
5. `judge_output` field is non-empty in `EvidenceBundle` after dual run
6. `LearningClosureBridge` writes route metadata including both proposer models
7. End-to-end test: run a task with `NEXUS_DUAL_PROPOSER=1` env var, verify receipt contains both candidate hashes and judge selection
8. No `public_claim_allowed` unless hidden verifier AND claim gate both PASS

### Forbidden shortcuts:

- ❌ No Qwen-only shortcut (must have both Qwen 7B + DeepSeek 6.7B candidates)
- ❌ No memory-only eval (must run full pipeline, not isolated eval scripts)
- ❌ No report-only claim (must have `artifacts/runtime/` execution trace with both models)
- ❌ No manual receipt treated as runtime (CLI invocation contracts ≠ automatic routing)
- ❌ No public claim unless hidden verifier and claim gate pass
