# RRL2 — Full Repair Loop Evidence Harness

**Status**: `RRL2_EVIDENCE_HARNESS_READY`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

Evidence harness implemented. Every repair attempt can now produce a complete 35-field evidence bundle with auto-derived bottleneck classification. No ranking/prompt/verifier changes.

---

## Implementation

| Component | Status |
|-----------|--------|
| EvidenceBundle dataclass | IMPLEMENTED |
| EvidenceHarness class | IMPLEMENTED |
| bottleneck auto-classification | IMPLEMENTED |
| per-task artifact output | IMPLEMENTED |
| tests | 11/11 PASS |

---

## Evidence Bundle Fields (35)

| Category | Fields |
|----------|--------|
| Input | task_id, repo, issue_summary, failing_test, expected_behavior, task_class, difficulty, timestamp |
| Route | route_selected, route_reason, judge_output, route_confidence |
| Anchor | selected_anchor, anchor_score, anchor_file, anchor_line_span, total_candidates, selection_reason |
| Evidence | codeintel_nodes, codeintel_edges, memory_items, missing_context_risks, evidence_confidence |
| Memory | available, retrieval_sources, selected_ids, provenance_count, rerank_mode, no_memory_match, influence_status |
| Prompt | length, memory_section, failure_section, evidence_section |
| Model | name, output_length, patch_produced, patch_format_valid, abstain_detected |
| Candidate | total, selected_id, selection_method, arbitration_used |
| Patch | applied, len, method, rollback, error |
| Verifier | status, command, collected, passed, failed, elapsed |
| Receipt | path, claim_eligible, gate_passed, failure_reason |
| Bottleneck | final_status, primary_bottleneck, secondary_bottlenecks, confidence, human_readable_reason |

---

## Bottleneck Auto-Classification

| Condition | Classification |
|-----------|---------------|
| verifier_status=PASS | SOLVED |
| patch_applied + verifier_fail + !patch_format_valid | VERIFIER_FAIL / patch_format |
| patch_applied + verifier_fail + memory_available + !memory_selected | VERIFIER_FAIL / evidence_memory |
| !patch_produced | MODEL_WRONG |
| patch_produced + !patch_applied | PATCH_APPLY_FAIL |
| abstain_detected | MODEL_ABSTAIN |

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
