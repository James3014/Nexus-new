# Nexus BMF0 Memory Stack Evidence — 7 Questions Answered

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BMF0_REPAIR_MEMORY_GAP_MISATTRIBUTED

---

## Q1: local_heal 使用的 3 個 Memory 模組

| Module | File | Call Site | Input | Output |
|--------|------|-----------|-------|--------|
| MemoryRetrievalAdapter | memory_retrieval_adapter.py | semantic_anchor_selection.py:128 | query_text, limit, anchor_symbol, anchor_file | list[RetrievedLesson] |
| FailureMemory | failure_memory.py | prompt_builder.py:4,121 | project_root | str (failure patterns) |
| LearningClosureBridge | learning_closure_bridge.py | orchestrator.py:442 | HealContext | dict (lesson written) |

### Schema Detail

**MemoryRetrievalAdapter**
- Input: `query_text: str`, `limit: int (5)`, `anchor_symbol: str`, `anchor_file: str`, `max_chars: int (800)`
- Output: `list[RetrievedLesson]` with fields: `finding_id`, `summary`, `relevance_score`, `provenance`, `source`, `pattern_type`
- Storage: `.nexus/reports/learn/learning_closure.jsonl`
- Scoring: token overlap + anchor symbol/file boost + failure penalty
- Dedup: summary fingerprint

**FailureMemory**
- Input: `project_root: Path`
- Output: `str` format: `[PAST FAILURES - DO NOT REPEAT]\n- {reason} (x{count})`
- Storage: `.nexus/metrics/skill_outcome_events.jsonl`
- Scoring: frequency count (Counter.most_common)

**LearningClosureBridge**
- Input: `ctx: HealContext` (failure_reason, solve_eligible, final_patch)
- Output: `dict` with: lesson_id, task_id, classification, summary, provenance, receipt_id
- Storage: `.nexus/reports/learn/learning_closure.jsonl`
- Write-only (no retrieval)

---

## Q2: Data Flow (Closure -> Retrieval 沒有 Feedback Loop)

```
orchestrator
    -> MemoryRetrievalAdapter.retrieve_reranked()
    -> LocalJsonlLessonStore.query()
    -> learning_closure.jsonl (READ)
    -> EvidencePacket.memory section
    -> PromptBuilder (inject into prompt)
    -> Model (generate patch)
    -> Verifier (pass/fail)
    -> orchestrator
    -> LearningClosureBridge.write_lesson()
    -> learning_closure.jsonl (WRITE)
```

**Critical Gap**: Step 10 writes to same JSONL as Step 3 reads, but **no weight/score update happens**. Verifier outcomes do not influence future retrieval ranking.

The cycle exists: read JSONL -> prompt -> model -> verifier -> write JSONL. But the write does not update any scoring weights that the read uses.

---

## Q3: helped/harmed/neutral 欄位

**DOES NOT EXIST**.

Current fields in learning_closure.jsonl:
- `lesson_id`, `task_id`, `classification`, `summary`, `provenance`, `receipt_id`
- No `helped`, `harmed`, `neutral`, `usefulness`, `outcome` fields

Closest field: `RetrievedLesson.pattern_type` (success/failure) — but this is INPUT classification, not OUTPUT outcome.

**Best artifact to carry**: `learning_closure.jsonl` — add `memory_retrieved_count`, `memory_helped`, `memory_harmed` fields to `LearningClosureBridge.write_lesson()` output.

Alternative: `receipt.json` — add `memory_influence` section to receipt schema.

---

## Q4: BMC REPAIR_MEMORY_GAP Attribution

**WEAK — cannot reconstruct per-task traces**.

BMC task directories (`artifacts/runtime/bmc_larger_heldout_frozen_validation_v0/tasks/`) are **empty**. No per-task:
- memory retrieval traces
- receipt files
- verifier results
- model outputs

Attribution was based on task class name (`evidence_memory`), not actual memory trace evidence.

**Recommendation**: Do NOT attribute to REPAIR_MEMORY_GAP without per-task traces. Reclassify as UNCERTAIN or add instrumentation first.

---

## Q5: Receipt 是否能記錄 Memory Influence

**BOTH missing**:

1. **Receipt schema lacks memory fields**: `receipt.py` has `learning_closure`, `autoreason_advisory`, `belief_trace`, `claim_delivery_gate` — but NO `memory_retrieval_trace`, `memory_helped_harmed`, `memory_influence_on_model`

2. **local_heal does not write memory influence**: `orchestrator.py` calls `MemoryRetrievalAdapter` but does not write `last_metadata` to `ctx` before receipt generation

**Fix locations**:
- `receipt.py` — add `memory_influence` section
- `orchestrator.py` — write `MemoryRetrievalAdapter.last_metadata` to `ctx`

---

## Q6: Learning Closure 的 Verifier Feedback

**EXISTS but NOT WIRED to retrieval**.

Learning Closure records:
- `classification`: verifier_pass, verifier_fail, parser_fail, owner_gated, correct_abstain, unsupported, evidence_gap, action_protocol_gap, verifier_gap
- `summary`: failure_reason text

**Why retrieval doesn't use it**:
1. No scoring weight update on write
2. No timestamp/recency weighting on read
3. No helped/harmed outcome recorded
4. Retrieval uses token overlap, not semantic similarity

The feedback exists in the data but is not wired into ranking.

---

## Q7: 最小改動增加 Observability

**Add `memory_retrieved` + `memory_influence` to receipt schema**.

### Files to Change

1. **`nexus/services/local_heal/receipt.py`** (~5 lines)
   - Add `memory_retrieval` section to receipt dict
   - Include: `lessons_retrieved`, `rerank_mode`, `anchor_symbol`, `no_memory_match`

2. **`nexus/services/local_heal/orchestrator.py`** (~5 lines)
   - Before receipt generation, write `MemoryRetrievalAdapter.last_metadata` to `ctx`
   - This makes memory trace available to receipt

### Change Size
~10 lines total

### Behavior Change
**NONE** — purely observational, no routing or scoring change

### What It Proves
- Whether memory was retrieved
- How many lessons
- What scores
- Whether model used them

### Next Step After
Analyze receipt traces to confirm/reject REPAIR_MEMORY_GAP attribution

---

## Summary

| Question | Answer |
|----------|--------|
| Q1: 3 modules | MemoryRetrievalAdapter, FailureMemory, LearningClosureBridge |
| Q2: Data flow | Cycle WITHOUT feedback loop |
| Q3: helped/harmed | DOES NOT EXIST |
| Q4: BMC attribution | WEAK (empty task dirs) |
| Q5: Receipt memory | BOTH missing (schema + write) |
| Q6: Verifier feedback | EXISTS but NOT WIRED |
| Q7: Minimal change | Add memory fields to receipt (~10 lines) |

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
