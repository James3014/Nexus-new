# GPT Task: Upstream Artifact Gap Closure before S6.8-R and M4 Re-entry

**Date**: 2026-06-19
**Source**: ChatGPT response (msg 22)
**Task ID**: RECOVERY-UPSTREAM-01

---

## GPT 判定

Phase Evidence Audit Yellow 後，下一步不是直接 S6.8-R，也不是 M4。先做 Upstream Artifact Gap Closure：盤點 raw evidence，決定 M3 / S6.7 / S6.x 是可從 raw materialize、需要 minimal rerun，還是只能保留 missing。

**M3 和 S6.7 必須 disk-backed Green，S6.x 可選擇 shadow comparison Green 或保守 defer。只有 upstream closure Green 後，才能進 S6.8-R backfill；M4 繼續 blocked。**

---

## Recovery Order

1. 先補 / 重跑 / materialize M3、S6.7、S6.x 的 disk-backed artifacts
2. 再做 S6.8-R selector freeze backfill
3. S6.8-R validation pass 後，才 M4 re-entry

---

## 10 Phases

### Phase 0: Raw evidence availability audit
- Search artifacts/, docs/reports/, receipts/, logs/, runs/ for raw evidence
- For each candidate: path, phase_hint, source_type, usable_for_backfill, evidence_strength
- Hard rule: chat_reference cannot be usable_for_backfill=true

### Phase 1: Decide recovery mode per phase
- M3: materialize_from_raw / rerun_minimal / remain_missing
- S6.7: materialize_from_raw / rerun_minimal / remain_missing
- S6.x: materialize_from_raw / rerun_minimal_shadow_only / remain_missing
- Hard rule: No phase can be marked Green by reconstruction from chat-only evidence

### Phase 2: M3 artifact closure
- Required: 18 artifacts + 11 tests + validation
- If materializing: include raw_source_paths, evidence_hashes, no_chat_only_evidence=true
- If rerunning: run_group=M3_RECOVERY_SOURCE_FRESH_EXPANSION

### Phase 3: S6.7 artifact closure
- Required: 18 artifacts + 11 tests + validation
- Prerequisite: M3 disk-backed Green or sufficient source-fresh recovery evidence
- If rerunning: run_group=S6_7_RECOVERY_BROADER_GATED_SELECTOR

### Phase 4: S6.x checkpoint comparison closure
- Required: 18 artifacts + 11 tests + validation
- S6.x is shadow-only
- Allowed outcomes: S6.x Recovery Green OR S6.x deferred with conservative checkpoint disposition

### Phase 5: Upstream closure summary
- For each phase: recovery verdict, artifact counts, test counts, validation pass
- Decision: proceed_to_S6_8_R_backfill=true/false

### Phase 6: Attribution and governance guard
- Validate: no chat-only evidence, no fabricated counts, no checkpoint adoption, no production routing

### Phase 7: Validation script
- scripts/validate/validate_upstream_gap_closure.py
- Red-level: fabricated evidence, checkpoint adoption, production routing, public claim

### Phase 8: Tests (8 files)
- Test cases: chat_only_evidence, fabricated counts, checkpoint adoption, production routing

### Phase 9: Report
- docs/reports/upstream_artifact_gap_closure_before_s6_8r.md

### Phase 10: Next plan only
- If Green: s6_8r_backfill_after_upstream_closure_plan.md
- If Yellow: upstream_gap_remaining_fixup_plan.md
- If Red: upstream_false_green_remediation_plan.md

---

## Success Criteria

### Green:
- M3 disk-backed recovery Green
- S6.7 disk-backed recovery Green
- S6.x either disk-backed Green or explicitly deferred
- No fabricated evidence
- No chat-only Green
- No governance violation
- S6.8-R can proceed

### Yellow:
- M3 or S6.7 partially recovered
- S6.x deferred
- Governance clear
- Clear remaining fixup path

### Red:
- Fabricated evidence
- Chat-only Green reused
- Checkpoint adoption / production routing / public claim violation
- M4 executed despite blocked prerequisite
- S6.8-R marked Green while M3/S6.7 missing

---

## Non-negotiable Boundaries

- simulated=false (unless reconstruction placeholder)
- claim_eligible=false
- public_claim_allowed=false
- no SWE-bench claim
- no Qwen solve-rate claim
- no checkpoint adoption
- no production routing
- no source-stale active success
- no model-generated SEARCH apply
- no ChatGPT-only evidence used as Green
- S5 checkpoint remains quarantined

---

## Deliverables

1. artifacts/runtime/upstream_gap_raw_evidence_audit.json
2. docs/reports/upstream_gap_raw_evidence_audit.md
3. artifacts/runtime/upstream_gap_recovery_mode_decision.json
4. docs/reports/upstream_gap_recovery_mode_decision.md
5. M3 artifacts (18 files)
6. M3 tests (11 files)
7. S6.7 artifacts (18 files)
8. S6.7 tests (11 files)
9. S6.x artifacts (18 files)
10. S6.x tests (11 files)
11. artifacts/runtime/upstream_gap_closure_summary.json
12. docs/reports/upstream_gap_closure_summary.md
13. artifacts/runtime/upstream_gap_closure_attribution_guard.json
14. docs/reports/upstream_gap_closure_attribution_guard.md
15. scripts/validate/validate_upstream_gap_closure.py
16. artifacts/validation/upstream_gap_closure_result.json
17. artifacts/validation/upstream_gap_closure_summary.md
18. tests/unit/test_upstream_gap_raw_evidence_audit.py
19. tests/unit/test_upstream_gap_recovery_mode_decision.py
20. tests/unit/test_upstream_gap_closure_summary.py
21. tests/unit/test_upstream_no_chat_only_green.py
22. tests/unit/test_upstream_no_fabricated_counts.py
23. tests/integration/test_upstream_gap_closure_attribution_guard.py
24. tests/integration/test_upstream_no_checkpoint_adoption.py
25. tests/integration/test_upstream_no_production_routing.py
26. docs/reports/upstream_artifact_gap_closure_before_s6_8r.md
27. artifacts/runtime/upstream_artifact_gap_closure_before_s6_8r_result.json
28. Next plan (conditional)

---

## Short Decision Sentence

Phase Evidence Audit Yellow 後，下一步不是直接 S6.8-R，也不是 M4。先做 Upstream Artifact Gap Closure：盤點 raw evidence，決定 M3 / S6.7 / S6.x 是可從 raw materialize、需要 minimal rerun，還是只能保留 missing。M3 和 S6.7 必須 disk-backed Green，S6.x 可選擇 shadow comparison Green 或保守 defer。只有 upstream closure Green 後，才能進 S6.8-R backfill；M4 繼續 blocked。
