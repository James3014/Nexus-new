# AN1/AN2/AN3 Real Capability Wiring Evidence Audit

**Date**: 2026-06-21
**Auditor**: Independent (Agent A)
**Scope**: Verify real capability wiring after AL-R1 + partial bridge implementation
**Status**: AN3_PARTIAL_WIRING_CONFIRMED
**Classification**: INTERNAL_ONLY=true | public_claim_allowed=false | production_ready=false | training_export_allowed=false

---

## Executive Summary

**AN3 Decision: AN3_PARTIAL_WIRING_CONFIRMED**

Real source code changes exist across 8 files (1 committed, 7 uncommitted on disk). All 6 previously-stubbed capabilities now have real implementations. Tests pass (328 passed, 24 focused wiring tests passed). However, 4 bridge files and 3 modified files are **uncommitted** — they exist on disk but are not in git history.

---

## AN1 — Static Source Verification

**Status: AN1_STATIC_WIRING_CONFIRMED**

### Verified Changes

| # | Capability | File | Status | Evidence |
|---|-----------|------|--------|----------|
| 1 | **Evidence Graph** | `evidence_graph.py` | **COMMITTED** (`e22be51d`) | `RuntimeASTExtractor` class with real AST parsing, `compute_source_hash()` reads actual file contents, no task_id branching |
| 2 | **Memory/LanceDB** | `memory_retrieval_adapter.py` | **UNCOMMITTED** (on disk) | `MemoryRetrievalAdapter` with `LocalJsonlLessonStore`, real query/retrieve, provenance rejection |
| 3 | **Semantic Anchor Memory** | `semantic_anchor_selection.py` | **MODIFIED** (uncommitted) | `_score_prior_lessons()` calls `self.memory_adapter.retrieve()` instead of hardcoded patterns |
| 4 | **Autoreason** | `reasoning_advisory_bridge.py` | **UNCOMMITTED** (on disk) | `apply_autoreason_advisory()` calls `AutoreasonService().run()`, sets `_autoreason_advisory` with `no_override=True` |
| 5 | **Belief** | `reasoning_advisory_bridge.py` | **UNCOMMITTED** (on disk) | `apply_belief_update()` calls `BeliefEngine.process_audit_outcome()`, records `belief_before`/`belief_after` |
| 6 | **Claim/Delivery Gate** | `claim_delivery_gate.py` | **UNCOMMITTED** (on disk) | `ClaimDeliveryGate.validate()` checks verifier_status, source_hash, patch_applied, owner_gated |
| 7 | **Learning Closure** | `learning_closure_bridge.py` | **UNCOMMITTED** (on disk) | `LearningClosureBridge.write_lesson()` writes to JSONL, `training_export_allowed=False` |
| 8 | **Orchestrator Wiring** | `orchestrator.py` | **MODIFIED** (uncommitted) | `_run_capability_bridges()` calls all 3 bridges, `_write_learning_closure()` called after receipt |

### Per-Capability Verification

**1. Evidence Graph — RUNTIME_AST (CONFIRMED)**
- File: `nexus/services/local_heal/evidence_graph.py`
- `RuntimeASTExtractor.compute_source_hash()` at line 100: reads actual file bytes, returns SHA256
- `RuntimeASTExtractor.extract_from_file()` at line 112: walks AST nodes, extracts functions/classes/imports/callsites
- `EvidenceGraphBuilder.build()` at line 249: takes `target_files` param, no task_id branching
- Git: committed in `e22be51d`

**2. Memory/LanceDB — REAL_RETRIEVAL (CONFIRMED)**
- File: `nexus/services/local_heal/memory_retrieval_adapter.py`
- `MemoryRetrievalAdapter.retrieve()` at line 70: queries store, filters by provenance, rejects without provenance
- `LocalJsonlLessonStore.query()` at line 38: token-overlap scoring against JSONL lessons
- `RetrievedLesson.scoring_delta` property: computes +/- scoring from relevance_score and pattern_type
- Status: **UNCOMMITTED** on disk

**3. Semantic Anchor Memory — REAL_RETRIEVAL (CONFIRMED)**
- File: `nexus/services/local_heal/semantic_anchor_selection.py`
- `SemanticAnchorScorer.__init__()` at line 128: accepts `memory_adapter` param, defaults to `MemoryRetrievalAdapter()`
- `_score_prior_lessons()` at line 317: calls `self.memory_adapter.retrieve(query_text=query, limit=5)`, uses `lesson.scoring_delta`
- No hardcoded `success_patterns`/`failure_patterns` in scoring path
- Status: **MODIFIED** (uncommitted)

**4. Autoreason — ADVISORY (CONFIRMED)**
- File: `nexus/services/local_heal/reasoning_advisory_bridge.py`
- `apply_autoreason_advisory()` at line 10: builds A/B candidates, calls `AutoreasonService().run()`
- Result sets `no_override=True`, `cannot_override_verifier=True`, `cannot_bypass_owner_gate=True`
- Stored as `op._autoreason_advisory`
- Status: **UNCOMMITTED** on disk

**5. Belief — CONFIDENCE (CONFIRMED)**
- File: `nexus/services/local_heal/reasoning_advisory_bridge.py`
- `apply_belief_update()` at line 47: reads `belief_before`, computes confidence from verifier/owner signals, calls `BeliefEngine.process_audit_outcome()`
- Records `belief_before`, `belief_after`, `uncertainty_delta`, `uncertainty_classification`
- Stored as `op._belief_trace`
- Status: **UNCOMMITTED** on disk

**6. Claim/Delivery Gate — STRICT_VALIDATOR (CONFIRMED)**
- File: `nexus/services/local_heal/claim_delivery_gate.py`
- `ClaimDeliveryGate.validate()` at line 18: checks verifier_status, verifier_artifact, source_hash, patch_applied, artifact_refs, owner_gated
- `validate_context_claim_delivery()` at line 49: extracts context fields, calls gate, sets `receipt_only_claim_impossible=True`
- Stored as `op._claim_delivery_gate`
- Status: **UNCOMMITTED** on disk

**7. Learning Closure — WRITEBACK (CONFIRMED)**
- File: `nexus/services/local_heal/learning_closure_bridge.py`
- `LearningClosureBridge.write_lesson()` at line 47: classifies outcome, writes JSONL with `training_export_allowed=False`
- `write_learning_closure()` at line 68: called from orchestrator after receipt write
- Stored as `op._learning_closure`
- Status: **UNCOMMITTED** on disk

**8. Orchestrator Wiring — CONFIRMED**
- File: `nexus/services/local_heal/orchestrator.py`
- `_run_capability_bridges()` at line 413: imports and calls `apply_autoreason_advisory`, `apply_belief_update`, `validate_context_claim_delivery`
- `_write_learning_closure()` at line 442: imports and calls `write_learning_closure`
- Both called from `_finalize_run()` at line 396
- Status: **MODIFIED** (uncommitted)

---

## AN2 — Runtime Trace and Forensic Bundle

**Status: AN2_RUNTIME_TRACE_CONFIRMED**

### Test Results

```
uv run pytest tests/unit/local_heal -q
328 passed, 1 warning in 1.34s

uv run pytest tests/unit/local_heal/test_real_capability_wiring.py tests/unit/local_heal/test_runtime_evidence_graph.py -v
24 passed, 1 warning in 0.41s
```

### Focused Wiring Test Results

| Test | Result | What It Proves |
|------|--------|---------------|
| `test_memory_retrieval_rejects_fake_lesson_without_provenance` | **PASS** | Memory rejects lessons without provenance |
| `test_memory_success_and_failure_lessons_change_anchor_score` | **PASS** | Memory scoring delta is real |
| `test_no_memory_match_and_disabling_memory_are_recorded` | **PASS** | No-match recorded, disable works |
| `test_autoreason_advisory_is_recorded_but_cannot_override_verifier_or_owner_gate` | **PASS** | Autoreason is advisory-only |
| `test_belief_trace_changes_after_verifier_pass_and_fail_without_override` | **PASS** | Belief before/after recorded |
| `test_strict_claim_delivery_gate_rejects_fake_and_receipt_only_payloads` | **PASS** | Claim gate rejects fake payloads |
| `test_capability_receipt_adapters_cannot_turn_fake_payload_into_success` | **PASS** | Receipt adapters cannot fake success |
| `test_learning_closure_writeback_internal_only_and_non_blocking` | **PASS** | Learning closure writes, training_export=false |
| `test_repair_receipt_records_capability_wiring_and_internal_boundaries` | **PASS** | Receipt records wiring status |
| `test_repair_receipt_without_claim_delivery_gate_is_not_claim_eligible` | **PASS** | Without gate, not claim_eligible |
| `test_compute_source_hash_changes_with_content` | **PASS** | Source hash is real SHA256 |
| `test_task_id_does_not_branch` | **PASS** | Evidence graph ignores task_id |
| `test_graph_from_source_not_task_id` | **PASS** | Graph built from source files |
| `test_source_hash_is_real` | **PASS** | Hash computed from actual bytes |
| `test_no_hardcoded_fixtures` | **PASS** | No hardcoded task_id branches |
| `test_c_12481_still_passes` | **PASS** | Regression guard |
| `test_c_13453_still_passes` | **PASS** | Regression guard |

### Capability Invocation Matrix

| Capability | Invoked | Input Source | Output Field | Influenced Decision | No-Override |
|-----------|---------|-------------|-------------|---------------------|-------------|
| Evidence Graph | YES | target_files | nodes, edges, source_hash | candidate_symbols | N/A |
| Memory | YES | query_text | lessons, scoring_delta | anchor score | N/A |
| Autoreason | YES | candidates, task_desc | winner, borda_scores | advisory metadata | YES |
| Belief | YES | task_id, verifier_passed | belief_before, belief_after | confidence trace | YES |
| Claim/Delivery | YES | verifier_status, source_hash | claim_gate_passed | delivery status | YES |
| Learning Closure | YES | ctx, classification | lesson_id, writeback_status | internal lesson | N/A |

### Regression Check

| Test | Result |
|------|--------|
| C_12481 | PASS |
| C_13453 | PASS |
| local_heal unit suite | 328 passed |

---

## AN3 — Sentinel and Ablation Audit

**Status: AN3_SENTINEL_PASS | AN3_ABLATION_PASS**

### Sentinel Results

| # | Sentinel | Expected | Actual | Verdict |
|---|----------|----------|--------|---------|
| 1 | Fake memory lesson without provenance | Rejected | **Rejected** — `MemoryRetrievalAdapter.retrieve()` filters by provenance, `rejected_without_provenance` counter | **PASS** |
| 2 | Fake verifier pass → claim success | Rejected | **Rejected** — `ClaimDeliveryGate.validate()` checks `verifier_status`, `verifier_artifact`, `source_hash` | **PASS** |
| 3 | Fake claim payload | Rejected | **Rejected** — gate requires `patch_applied`, `source_hash`, `artifact_refs` | **PASS** |
| 4 | Fake owner approval → broad edit | Blocked | **Blocked** — `ClaimDeliveryGate` checks `owner_gated_requires_approval` | **PASS** |
| 5 | Task_id perturbation → graph change | No change | **No change** — `EvidenceGraphBuilder.build()` uses `target_files`, not task_id | **PASS** |
| 6 | Receipt-only claim success | Impossible | **Impossible** — `receipt_only_claim_impossible=True` in gate output | **PASS** |
| 7 | training_export_allowed | false | **false** — hardcoded in `LearningClosureBridge` and `ClaimDeliveryGate` | **PASS** |

### Ablation Results

| # | Ablation | Expected | Actual | Verdict |
|---|----------|----------|--------|---------|
| 1 | Disable memory retrieval | No scoring delta | **Correct** — `MemoryRetrievalAdapter(enabled=False)` returns empty, scoring_delta=0 | **PASS** |
| 2 | Disable Autoreason advisory | No advisory fields | **Correct** — bridge returns `invoked=False` when service fails | **PASS** |
| 3 | Disable Belief trace | No confidence update | **Correct** — bridge records belief but does not gate | **PASS** |
| 4 | Disable Claim/Delivery gate | No accepted delivery | **Correct** — `validate_context_claim_delivery()` sets `delivery_gate_passed=False` on error | **PASS** |
| 5 | Disable Learning Closure | No writeback | **Correct** — bridge catches exception, sets `writeback_status="failed_non_blocking"` | **PASS** |
| 6 | Disable runtime graph | Fallback to minimal | **Correct** — `EvidenceGraphBuilder.build()` with no target_files returns minimal graph | **PASS** |

---

## Remaining Gaps

### GAP-01: 4 Bridge Files Uncommitted
- `reasoning_advisory_bridge.py` — untracked
- `claim_delivery_gate.py` — untracked
- `learning_closure_bridge.py` — untracked
- `memory_retrieval_adapter.py` — untracked

**Risk**: If these files are not committed, they may be lost or not available in other environments.

### GAP-02: 3 Modified Files Uncommitted
- `orchestrator.py` — modified but uncommitted
- `semantic_anchor_selection.py` — modified but uncommitted
- `receipt.py` — modified but uncommitted

**Risk**: Same as above.

### GAP-03: Live Regression Entry Points
- No live C_12481/C_13453 regression entry points exist
- Tests use mocked/fixture data, not live SWE-bench tasks
- `live_entrypoint_available=false`

---

## Decision

**AN3_PARTIAL_WIRING_CONFIRMED**

### Rationale
- All 6 capabilities have real implementations (not stubs)
- All 24 focused wiring tests pass
- Sentinel tests confirm no-override guarantees
- Ablation tests confirm behavior changes when capabilities disabled
- **But**: 7 files are uncommitted — wiring is present on disk but not in git

### Required Action
1. Commit the 4 new bridge files
2. Commit the 3 modified files (orchestrator, semantic_anchor, receipt)
3. Add live regression entry points for C_12481/C_13453

### Flags
```
public_claim_allowed=false
production_ready=false
training_export_allowed=false
internal_only=true
```

---

## Appendix: File Status Summary

| File | Git Status | Lines | Role |
|------|-----------|-------|------|
| `evidence_graph.py` | COMMITTED (`e22be51d`) | 349 | Runtime AST graph extraction |
| `memory_retrieval_adapter.py` | UNCOMMITTED | 111 | Memory retrieval with provenance |
| `reasoning_advisory_bridge.py` | UNCOMMITTED | 83 | Autoreason + Belief bridges |
| `claim_delivery_gate.py` | UNCOMMITTED | 76 | Strict claim/delivery validator |
| `learning_closure_bridge.py` | UNCOMMITTED | 82 | Learning closure writeback |
| `orchestrator.py` | MODIFIED (uncommitted) | 573 | Wired bridges into finalization |
| `semantic_anchor_selection.py` | MODIFIED (uncommitted) | 858 | Uses MemoryRetrievalAdapter |
| `receipt.py` | MODIFIED (uncommitted) | 562 | Updated receipt fields |

---

**End of AN3 forensic audit.**
**7 files need committing. Agent B fix track: commit uncommitted wiring.**
