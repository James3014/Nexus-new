# Nexus Local Qwen Repair — Agent Handoff Summary

**Date**: 2026-06-19
**Purpose**: Provide new GPT agent with current state for Patch Protocol Stabilization Intake

---

## 1. M5 Closure State

```
M5_final_state: SEALED
M5_verdict: GREEN
total_tasks: 12
solved: 10/12 (83%)
verified_solve_count: 10
not_solved: 2 (eval, evalf — both semantic_wrong, retry_exhausted)
governance: PASS
m6_executed: false
training_candidates: 10 (export_now=false, human_review_required=true)
git_commit: aecba529 "seal M5 controlled repair stage archive"
```

**Key**: M5 is sealed. 10 verifier-backed solves. eval/evalf retry exhausted. No M6 started.

---

## 2. v4 Retry Evidence (3 cases)

v4 retry was done in `artifacts/runtime/advisor_evidence_v4/`:
- `verifier_guided_retry_results_v1.jsonl` — 3 retry results
- `abbreviated_trace_retry_pack.md` — abbreviated traceback evidence
- `patches/` — patch files

v4 proved: abbreviated traceback retry can convert behavioral failure → solve on some cases.

---

## 3. Line-Span Protocol v1 Results (from Agent A)

From `artifacts/runtime/advisor_evidence_v5/line_span_patch_protocol_results.jsonl`:

| Case | v4 Result | v5 Line-Span | Verifier After | Delta |
|------|-----------|--------------|----------------|-------|
| astropy-13236 / 7B | APPLIED | APPLIED | VERIFIER_REJECTION_BEHAVIORAL | NEUTRAL |
| astropy-13236 / 14B | PATCH_APPLY_FAIL | APPLIED | VERIFIER_REJECTION_BEHAVIORAL | **STABILITY_LIFT** |
| astropy-14182 / 14B | APPLIED | APPLIED | VERIFIED_SOLVE | NEUTRAL (REGRESSION_FREE) |

**Key findings**:
- Line-span protocol eliminated hunk-offset PATCH_APPLY_FAIL
- astropy-14182 verified solve preserved (regression-free)
- Protocol fixes apply stability, NOT behavioral correctness
- astropy-13236 still fails verifier (UnitConversionError — semantic issue)

---

## 4. ASTLocator / Line-Span Prototype Status

**Runtime modules**: NOT IMPLEMENTED
- `nexus/services/local_heal/ast_locator.py` — NOT FOUND
- `nexus/services/local_heal/source_hash_guard.py` — NOT FOUND
- `nexus/services/local_heal/patch_intent.py` — NOT FOUND

**Bench script**: EXISTS
- `scripts/bench/line_span_patch_protocol_v1.py` — line-span v1 prototype

**ADR**: NOT FOUND in repo root

**Phase 0 contract**: EXISTS
- `artifacts/runtime/advisor_evidence_v5/astlocator_phase0_contract.json`

**Hardening recommendations**: EXISTS
- `artifacts/runtime/advisor_evidence_v5/line_span_protocol_hardening_recommendations.json`

---

## 5. What Exists vs What's Missing

| Component | Status | Path |
|-----------|--------|------|
| Line-span bench script | ✅ EXISTS | `scripts/bench/line_span_patch_protocol_v1.py` |
| Line-span v1 results | ✅ EXISTS | `artifacts/runtime/advisor_evidence_v5/line_span_patch_protocol_results.jsonl` |
| ASTLocator Phase 0 contract | ✅ EXISTS | `artifacts/runtime/advisor_evidence_v5/astlocator_phase0_contract.json` |
| Hardening recommendations | ✅ EXISTS | `artifacts/runtime/advisor_evidence_v5/line_span_protocol_hardening_recommendations.json` |
| M5 stage closure | ✅ EXISTS | `artifacts/runtime/stage_closure/m5_stage_closure.json` |
| M5 execution records | ✅ EXISTS | `artifacts/runtime/m5_v2_execution_records.jsonl` |
| v4 retry results | ✅ EXISTS | `artifacts/runtime/advisor_evidence_v4/verifier_guided_retry_results_v1.jsonl` |
| **ast_locator.py** | ❌ NOT IMPLEMENTED | — |
| **source_hash_guard.py** | ❌ NOT IMPLEMENTED | — |
| **patch_intent.py** | ❌ NOT IMPLEMENTED | — |
| **unit tests** | ❌ NOT IMPLEMENTED | — |

---

## 6. Recommended Priority (from user)

```
P0 — Protocol Runtime Stabilization
1. Abbreviated Traceback Formatter v1
2. PatchIntent JSON parser
3. SourceHashGuard
4. ASTLocator / line-span apply
5. v4 cases A/B dry-run

P1 — M5 Data Closure
6. M5 re-entry manifest
7. Strategy-aware trace rows from M5
8. DPO/PPO draft rows, export_now=false

P2 — Strategy Runtime Contract
9. StrategyEnvelope trace-only
10. Strategy-conditioned SurgicalPacker
```

---

## 7. Non-Negotiable Boundaries

- No M6 execution
- No benchmark expansion
- No training export
- No public claim
- No production routing
- No checkpoint adoption
- solved=true only if verification_passed=true
- compile check ≠ verifier pass
- dependency failure ≠ model failure

---

## 8. Files for Reference

- M5 closure: `artifacts/runtime/stage_closure/m5_stage_closure.json`
- M5 records: `artifacts/runtime/m5_v2_execution_records.jsonl`
- v4 retry: `artifacts/runtime/advisor_evidence_v4/verifier_guided_retry_results_v1.jsonl`
- Line-span v1: `artifacts/runtime/advisor_evidence_v5/line_span_patch_protocol_results.jsonl`
- ASTLocator contract: `artifacts/runtime/advisor_evidence_v5/astlocator_phase0_contract.json`
- Hardening recs: `artifacts/runtime/advisor_evidence_v5/line_span_protocol_hardening_recommendations.json`
- Stage closure report: `/Users/jameschen/Downloads/M5_stage_closure_report_20260619.md`
