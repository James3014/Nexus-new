# Audit Report: 3B Judge + Qwen 7B + DeepSeek 6.7B + Nexus Armor Runtime Wiring Status

**Date**: 2026-06-22  
**Scope**: Read-only audit — no code edits, no benchmarks  
**Directories checked**: docs/reports/, artifacts/runtime/, .nexus/reports/local_heal/, nexus/services/local_heal/, scripts/eval/, nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md

---

## A. May Gemini Bare Claim

### Which file proves Nexus+Gemini beat Gemini bare?

**Primary**: `docs/reports/NEXUS_PUBLICATION_READY_12X2_SUMMARY_2026-05-20.md`

| Metric | Gemini bare | Gemini + Nexus |
|--------|------------|----------------|
| Verified delivery | 16/24 (66.7%) | 24/24 (100.0%) |
| Wall-time per row | 39.2984s | 0.9152s |

- **Task count**: 12-task × 2 runs = 24 task-arm pairs
- **Date/report**: 2026-05-20, publication-ready summary
- **Runtime evidence or report-only?**: **Report-only**. The report references "public candidate lane" and "frozen" tasks, but no runtime script or live execution receipt was found in scripts/eval/ or artifacts/runtime/ that corresponds to this specific comparison. The 12X2 summary is a post-hoc report artifact.

### Supporting reports (all report-only):
- `NEXUS_GEMINI3FLASH_VALUE_BENCHMARK_2026-04-28.md` — Gemini 3 Flash bare vs +Nexus
- `NEXUS_GEMINI31PRO_VALUE_BENCHMARK_2026-04-28.md` — Gemini 3.1 Pro bare vs +Nexus
- `GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-05-01.md` — Detailed task-level breakdown
- `GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-04-28.md` — Smoke test: Gemini+Nexus 3/3, Gemini bare 0/3

**Verdict**: Metrics are reported but classified as **report-only evidence**, not live runtime execution receipts. No hidden verifier or claim gate audit trail found for these specific comparisons.

---

## B. Historical Local Heterogeneous Evidence

### Files proving the route existed

| File | Route ID | Context |
|------|----------|---------|
| `docs/reports/r5_heterogeneous_shadow_route_v0.md` | `local_heterogeneous_portfolio_shadow_v0` | Shadow route definition |
| `docs/reports/r6_heterogeneous_shadow_benchmark_v0.md` | `qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b` | Benchmark: Route B dual_proposer Qwen 7B + DeepSeek 6.7B, 100% (6/6) |
| `docs/reports/t2_heterogeneous_experimental_route_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | Route contract, CLI flag, config override |
| `docs/reports/t3_expanded_heterogeneous_route_benchmark_v0.md` | `qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b` | 10 tasks, 100% across all arms |
| `docs/reports/t4_heterogeneous_route_final_policy_decision_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | Final policy decision |
| `docs/reports/u1_heterogeneous_route_hardening_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | Hardening |
| `docs/reports/u3_expanded_heterogeneous_route_benchmark_v0.md` | `qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b` | 12 tasks, weighted summary |
| `docs/reports/u4_heterogeneous_route_internal_adoption_decision_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | Internal adoption decision |
| `docs/reports/v3_heterogeneous_route_promotion_readiness_decision_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | Core model set: 3B judge + 7B primary + DeepSeek secondary |
| `docs/reports/w1_uncertainty_trigger_integration_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | Uncertainty trigger |
| `docs/reports/w2_internal_route_wiring_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | Internal wiring |
| `docs/reports/w4_internal_heterogeneous_route_decision_lock_v0.md` | `local_heterogeneous_portfolio_experimental_v0` | Decision lock |

### Route IDs

- `local_heterogeneous_portfolio_experimental_v0` — primary experimental route
- `local_heterogeneous_portfolio_shadow_v0` — shadow evaluation route
- `qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b` — benchmark route name (compound)
- `qwen_7b_plus_deepseek_6_7b_dual_proposer` — dual proposer sub-route

### Manual-only / experimental status

**Exact strings `manual_only_experimental` and `manual_invocation_only`**: NOT FOUND in any checked location. These exact phrases do not appear in docs/reports/, artifacts/runtime/, local_heal code, scripts/eval/, or Learning Closure Matrix.

However, the route IS effectively manual/experimental:
- All artifacts are in benchmark directories (r5, r6, t2-t4, u1-u4, v2-v3, w1-w4)
- Route contracts specify CLI flags and config overrides (manual invocation)
- `w2_internal_route_wiring_v0/route_dry_run_receipts/` — dry-run only, not live execution
- No runtime code implements the route

### Metrics and task count

| Benchmark | Tasks | Route B (dual_proposer) Result |
|-----------|-------|-------------------------------|
| r6 | 6 | 100% (6/6), 1830ms avg, 6.8s total |
| t3 | 4+4+2=10 | 100% (4/4 + 4/4 + 2/2), score 1.0000 |
| u3 | 8+4=12 | 100% (8/8 + 4/4), score 0.9000 |

---

## C. Current Runtime Wiring

### DeepSeek 6.7B allowed in backend resource policy

**NO.** `backend_resource_policy.py:48-94` defines DEFAULT_POLICIES for: qwen2.5:3b, qwen2.5-coder:7b, gemma4-coder-12b, deepseek-r1-14b-q4km (FORBIDDEN), gpt-4o, claude-3-5-sonnet. **deepseek-coder:6.7b-instruct has no entry.** `is_allowed("deepseek-coder:6.7b-instruct")` returns False (unknown model = forbidden by default at line 113).

### 3B judge role contract exists

**PARTIAL.** `role_contract.py:9` defines `SELECTOR = "selector" # 3B: candidate selection, reranking, budget policy`. This is the 3B role but it's called "selector", not "judge". The 3B model can serve as a selector, but there's no explicit "judge" role or judge-panel invocation in the runtime code.

### Qwen 7B proposer role exists

**NO.** `role_contract.py` defines SEARCHER for 7B, not PROPOSER. The 7B role is "search, localization, planning" — not proposal generation. No proposer concept exists in role_contract.

### DeepSeek secondary proposer role exists

**NO.** No DeepSeek model (6.7B or otherwise) has a role in role_contract. The only DeepSeek entry in backend_resource_policy is deepseek-r1-14b (FORBIDDEN).

### Dual proposer route exists as executable route

**NO.** `native_route_adapter.py` defines ROUTE_RULES for 3b/7b/12b per phase. No dual proposer routing. `committee_orchestrator.py` implements multi-sample committee (k=3) with 14B/7B mix — this is single-model multi-sample, NOT independent proposers. grep for `dual_proposer|deepseek.*6\.7|second_proposer|secondary_proposer` across all `local_heal/*.py` = **0 matches**.

### 3B judge actually invoked

**PARTIAL.** The 3B model (qwen2.5:3b) is ALLOWED in backend_resource_policy and has the SELECTOR role. However, no code path explicitly invokes a "judge" function. The reasoning_advisory_bridge.py uses `judge_count=3` but that's the AutoreasonService judge panel (different concept — autoreason judgment, not patch selection).

### Two candidate outputs persisted

**NO.** Candidate generation (`candidate_generation.py`, `candidate_search.py`) produces candidates sequentially. There's no dual-proposer pipeline that generates two independent candidate sets from different models and persists both.

### Judge selection persisted

**NO.** No judge selection receipt or persistence mechanism for 3B judge output. EvidenceBundle has a `judge_output: str = ""` field (evidence_harness.py:30) but it's always empty in actual runs (artifacts/runtime/rrl3_runs show `"judge_output": ""`).

### Selected candidate applied

**YES (single proposer only).** The standard pipeline applies a single candidate. No dual-proposer selection mechanism.

### Verifier executed

**YES.** `micro_verifier.py`, `phases/verification.py`, `evaluation_gate.py`, and 37+ files implement verifier logic. The verifier infrastructure is mature and extensively wired.

### Nexus armor gates/capabilities invoked

**YES (for standard pipeline).** governance_gate, claim_delivery_gate, runbook_compliance, evidence_harness, shadow_receipt — all wired in the standard single-model pipeline.

### Learning Closure written

**YES (for standard pipeline).** `learning_closure_bridge.py` implements classification and writeback. However, no learning closure was written for the dual proposer heterogeneous route specifically.

---

## D. MEMORY-EVAL-9/11 Reality

### Which models are actually called?

Both scripts use **ONLY `qwen2.5-coder:7b`** via Ollama:
- `run_memory_eval_9_real_model_ab.py:44` — `has_qwen = any("qwen2.5-coder:7b" in name for name in models)`
- `run_memory_eval_11_c13453_real_model_ab.py:41` — same check

### Is it Qwen-only memory A/B?

**YES.** Both scripts run exactly two arms:
- `nexus_memory_on`: MemoryRetrievalAdapter enabled, qwen2.5-coder:7b
- `nexus_memory_off`: MemoryRetrievalAdapter disabled, qwen2.5-coder:7b

No other models are invoked. No dual proposer, no deepseek, no 3B judge, no full Nexus armor.

### Is it full Nexus armor or isolated eval script?

**ISOLATED EVAL SCRIPT.** Both scripts directly instantiate:
- `HealOrchestrator` with minimal phases
- `GovernanceGate` (basic)
- `OllamaClient` (single model)
- `MemoryRetrievalAdapter` (the variable being tested)

They do NOT use the full local_heal pipeline (no candidate_generation, no agentless_pipeline, no committee_orchestrator, no native_route_adapter, no evidence_harness integration). The eval scripts are standalone evaluation harnesses, not the production runtime.

---

## E. Gap Verdict

### **Option 3: Historical/manual only, current runtime disconnected**

The route `3B judge + Qwen 7B + DeepSeek 6.7B + Nexus armor` exists exclusively in:
1. Historical benchmark reports (docs/reports/) — r5 through w4
2. Benchmark artifacts (artifacts/runtime/) — dry-run receipts, route configs, selection receipts
3. Route contracts and config files (artifacts/runtime/w2, t2, u1)

The runtime code in `nexus/services/local_heal/` has **none** of the following:
- deepseek-coder:6.7b-instruct in backend resource policy
- proposer role in role_contract
- dual proposer routing in native_route_adapter
- dual candidate generation and selection pipeline
- 3B judge invocation for patch selection

The gap is **complete** — not partially wired, not needing minor fixes. The entire dual-proposer heterogeneous pipeline was designed, benchmarked, and documented, but never implemented as executable runtime code.

---

## F. Implementation Plan

### Minimal files to touch (max 10)

| # | File | Change |
|---|------|--------|
| 1 | `nexus/services/local_heal/backend_resource_policy.py` | Add `deepseek-coder:6.7b-instruct` entry (ALLOWED, LOCAL_7B) |
| 2 | `nexus/services/local_heal/role_contract.py` | Add `PROPOSER = "proposer"` role, map 7B→PROPOSER, 6.7B→PROPOSER |
| 3 | `nexus/services/local_heal/dual_proposer_orchestrator.py` | **NEW** — Orchestrator that invokes both Qwen 7B and DeepSeek 6.7B independently, persists both candidate outputs |
| 4 | `nexus/services/local_heal/judge_selector.py` | **NEW** — 3B judge that receives both candidate sets and selects winner |
| 5 | `nexus/services/local_heal/native_route_adapter.py` | Add `dual_proposer` to ROUTE_RULES for applicable phases |
| 6 | `nexus/services/local_heal/orchestrator.py` | Add route dispatch: if dual_proposer route selected, delegate to DualProposerOrchestrator |
| 7 | `nexus/services/local_heal/evidence_harness.py` | Wire `judge_output` field to receive 3B judge selection receipt |
| 8 | `nexus/services/local_heal/candidate_generation.py` | Add dual-track candidate generation (parallel Qwen + DeepSeek) |
| 9 | `tests/unit/local_heal/test_dual_proposer.py` | **NEW** — TDD tests for dual proposer pipeline |
| 10 | `tests/unit/local_heal/test_judge_selector.py` | **NEW** — TDD tests for 3B judge selection |

### Acceptance gates

1. `deepseek-coder:6.7b-instruct` passes `BackendResourcePolicy.is_allowed()` → True
2. 3B model can be invoked as judge via `judge_selector.py` and selection receipt persisted
3. Two independent candidate outputs generated and stored in EvidenceBundle
4. Judge selection applied to final patch
5. Verifier runs on selected candidate
6. All existing tests pass (no regression)
7. `gitnexus_detect_changes()` confirms only expected symbols affected

### Forbidden shortcuts

- **No Qwen-only shortcut**: Cannot substitute Qwen 7B for both proposers and claim dual proposer
- **No memory-only eval**: Cannot use MEMORY-EVAL-9/11 (Qwen-only memory A/B) as evidence for dual proposer
- **No report-only claim**: Cannot cite historical benchmark reports as runtime evidence
- **No manual receipt treated as runtime**: Dry-run receipts in artifacts/runtime/ are not executable runtime
- **No public claim unless hidden verifier and claim gate pass**: Any public benchmark claim must pass hidden verifier and claim_delivery_gate
