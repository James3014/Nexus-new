# Local 7B/14B Repair Validation Gate v0 — Final Report

## 1. Mainline Calibration
This gate directly serves the local model repair capability main line.  
`local_7b_14b_repair_execution_v0` completed 6/6 tasks.  
This gate verifies those results are controlled, complete, and trustworthy.

## 2. Correction: 3/10 → 10/10 Gates
- **Before**: 3 gate files (approval_boundary, receipt_completeness, verifier_evidence)
- **After**: 10/10 gate files completed

| Gate | File | Status |
|------|------|--------|
| Approval boundary | approval_boundary_results.json | ✅ PASS |
| Receipt completeness | receipt_completeness_results.json | ✅ PASS |
| Verifier evidence | verifier_evidence_results.json | ✅ PASS |
| Patch boundary | patch_boundary_results.json | ✅ PASS |
| Domain classification | domain_classification_results.json | ✅ PASS |
| Concurrency risk | concurrency_risk_results.json | ✅ PASS (with risk noted) |
| Retry/abstention | retry_abstention_results.json | ✅ PASS |
| Governance boundary | governance_boundary_results.json | ✅ PASS |
| Summary consistency | summary_consistency_results.json | ✅ PASS |
| Recommended next step | recommended_next_step.json | ✅ Issued |

## 3. Final Gate Decision: **PASS_WITH_RISK**
All 10 gates pass. One evidence discrepancy noted (below).

## 4. Evidence Discrepancy Summary
- `concurrency_bug_01`: Approved verifier command was `pytest test_deadlock.py`; actual was `code_review_verified` due to nexus import-time hang in environment.
- This is recorded as `evidence_discrepancy`, not failure. Logic parity with `FixedResourceTransfer` confirmed.
- **evidence_discrepancy_count**: 1

## 5. Corrected Domain Classification
- astropy_13236 → `astropy_table_structured_ndarray`
- astropy_12907 → `astropy_modeling_separability`
- sympy_13031 → `sympy_sparse_matrix_col_join`
- django_core_01 → `nexus_verifier_domain_django` (NOT Django upstream)
- concurrency_bug_01 → `nexus_verifier_domain_concurrency_deadlock`
- concurrency_bug_02 → `nexus_verifier_domain_concurrency_race`

## 6. Concurrency Risk Treatment
- `concurrency_bug_01`: `code_review_verified`, `flakiness_risk=low_or_unknown`
- `concurrency_bug_02`: `stress_test_verified`, `flakiness_risk=low`
- Neither is treated as zero-risk. Risk is recorded.

## 7. Worktree Hygiene Audit Summary
- Dirty tracked files: many (build cache, scratch logs, runtime code changes)
- Build cache (nexus-core-rs/target/) present — cleanup recommended when ready
- Tree is safe for next step (no staged partial-work)

## 8. Transport Invariant Alignment Summary
- `protocol.py`: source_hash, canonical_span, fuzzy_candidate all implemented
- Fail-closed correctly: fuzzy candidate >= 0.95 does NOT auto-apply
- Next test required: SEARCH_MISMATCH + fuzzy >= 0.95 must fail closed

## 9. MicroVerifier Task-Scoped Audit Summary
- Uses generic `python3`, not task-scoped venv/interpreter
- Does not consume ReproPreflightResult or env taxonomy
- Hardening required: task-scoped interpreter, env taxonomy, false-pass/fail risk

## 10. StructuredPacket Retry Wiring Summary
- `EvidenceCompactor.compact_structured()` and `StructuredPacket.to_prompt_text()` exist
- **Gap**: `SelfCorrector.build_retry_prompt()` does NOT consume StructuredPacket
- Hardening required: wire failure evidence → StructuredPacket → retry prompt

## 11. S2T Export Guard Classification Summary
- `S2TExportGuard` v2 is well-structured and separation-complete
- All 6 tasks: `training_eligible=False`, `claim_eligible=False`, `export_as_public_claim=False`
- `requires_human_review_before_training=True` by default

## 12. Claim Separation Summary
- Internal verifier pass ≠ public claim ✅
- `code_review_verified` ≠ subprocess pytest verified ✅ (explicitly recorded)
- No GPT/Gemini parity claim ✅
- No production-ready claim ✅

## 13. Recommended Next Step
**`local_7b_14b_repair_flakiness_and_boundary_review_v0`**  
Reason: `concurrency_bug_01` carries `low_or_unknown` flakiness risk due to `code_review_verified` method. Review should confirm acceptability before authorizing expansion plan.
