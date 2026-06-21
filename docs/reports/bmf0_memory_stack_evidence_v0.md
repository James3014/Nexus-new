# BMF0 — Memory Stack Evidence Answers

**Status**: `BMF0_REPAIR_MEMORY_GAP_MISATTRIBUTED`
**Date**: 2026-06-21

---

## Q1: 3 Memory Modules Used by local_heal

| Module | Call Site | Input | Output |
|--------|-----------|-------|--------|
| MemoryRetrievalAdapter | semantic_anchor_selection.py:128 | query_text, limit, anchor_symbol, anchor_file | list[RetrievedLesson] |
| FailureMemory | prompt_builder.py:4,121 | project_root | str (failure patterns) |
| LearningClosureBridge | orchestrator.py:442 | HealContext | dict (lesson written) |

---

## Q2: Data Flow (No Feedback Loop)

```
orchestrator -> MemoryRetrievalAdapter -> LocalJsonlLessonStore
    -> learning_closure.jsonl -> EvidencePacket -> PromptBuilder
    -> Model -> Verifier -> orchestrator -> LearningClosureBridge
    -> learning_closure.jsonl (CYCLE WITHOUT FEEDBACK)
```

**Gap**: Verifier outcomes do not influence future retrieval ranking.

---

## Q3: helped/harmed/neutral

**DOES NOT EXIST**. Best artifact to carry: `learning_closure.jsonl` or `receipt.json`.

---

## Q4: BMC REPAIR_MEMORY_GAP Attribution

**WEAK**. BMC task directories are empty. Cannot reconstruct per-task traces. Do not attribute to memory without evidence.

---

## Q5: Receipt Memory Influence

**BOTH missing**: Receipt schema lacks memory fields AND local_heal does not write memory influence.

---

## Q6: Verifier Feedback in Learning Closure

**EXISTS** (classification, summary) but **NOT WIRED** to retrieval scoring.

---

## Q7: Minimal Observability Change

Add `memory_retrieved` + `memory_influence` to receipt schema (~10 lines, no behavior change).

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
