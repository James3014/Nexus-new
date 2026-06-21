# BMF0 — Memory Stack Evidence Report

**Status**: `BMF0_REPAIR_MEMORY_GAP_MISATTRIBUTED`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

BMC REPAIR_MEMORY_GAP attribution is weak. BMC task directories are empty - no per-task traces exist. The real gaps are: (1) no helped/harmed tracking, (2) no temporal decay, (3) no verifier feedback loop to memory ranking.

---

## BMF0-1: Existing Memory Architecture

| Module | Used by local_heal | Key Capability |
|--------|-------------------|----------------|
| MemoryRetrievalAdapter | YES | Token overlap + anchor boost |
| LearningClosureBridge | YES | Write lessons to JSONL |
| FailureMemory | PARTIAL | Load failure patterns |
| LessonRetrieval | UNKNOWN | Keyword + category matching |
| MemoryService | UNKNOWN | LanceDB + Redis |
| MemoryRepository | UNKNOWN | LanceDB storage |

---

## BMF0-2: Integration Trace

| Edge | Enabled | Gap |
|------|---------|-----|
| Orchestrator -> MemoryRetrievalAdapter | YES | No helped/harmed trace |
| MemoryRetrievalAdapter -> EvidencePacket | YES | No ranking trace |
| EvidencePacket -> PromptBuilder | YES | No memory influence trace |
| Orchestrator -> LearningClosureBridge | YES | No feedback loop |
| LearningClosureBridge -> MemoryRetrievalAdapter | **NO** | CRITICAL: No feedback loop |

---

## BMF0-4: BMC REPAIR_MEMORY_GAP Review

| Task | Evidence | Misattribution Risk |
|------|----------|---------------------|
| K004 | NO per-task trace | HIGH |
| K006 | NO per-task trace | HIGH |

**BMC task directories are empty. Attribution was based on class name, not evidence.**

---

## BMF0-5: Capability vs Need Matrix

| Gap Type | Count | Priority |
|----------|-------|----------|
| HELPED_HARMED_TRACKING | 1 | P0 |
| FORGETTING_DECAY | 1 | P1 |
| TRACE_OBSERVABILITY | 2 | P2 |
| VECTOR_SYNC | 1 | P2 |

---

## BMF0-7: Final Decision

**BMF0_REPAIR_MEMORY_GAP_MISATTRIBUTED**

### True Gaps

1. **No helped/harmed tracking** - Cannot measure if memory helped or harmed
2. **No temporal decay** - Stale memories not penalized
3. **No verifier feedback loop** - Learning closure does not update memory ranking
4. **No trace observability** - Memory traces not in receipts

### Not Gaps

- Retrieval: works
- Ranking: basic but functional
- Provenance: works
- Writeback: works
- Dedup: works

### Recommendation

Before implementing RepairMemory v2, first add helped/harmed tracking and verifier feedback loop to existing memory stack.

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
