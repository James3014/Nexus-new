# BMF7-MCA — Nexus Memory Capability Coverage Audit

**Status**: `BMF7_MCA_CORE_MEMORY_CONNECTED_ONLY`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

Full Nexus memory system is NOT integrated into local_heal. Only the core memory lane (FindingsMemory + LearningClosure + receipt) is connected. MemPalace, MemoryService, Learn Scheduler/SLO/KPI are NOT connected. Belief is trace-only (advisory).

---

## Integration Levels

| Level | Subsystems |
|-------|------------|
| L4 Connected | FindingsMemory, LearningClosure, native_evidence_packet, receipt.memory_influence |
| L3 Trace Only | Belief |
| L2 Advisory/Gate | Artifact, Claim |
| Not Connected | MemoryService, MemPalace, Learn Scheduler, Learn SLO/KPI |

---

## Key Findings

| Question | Answer |
|----------|--------|
| Full Nexus memory integrated? | **NO** |
| MemPalace connected? | **NO** |
| Belief in ranking? | **NO** (trace/advisory only) |
| Artifact in retrieval? | **NO** (evidence/claim only) |
| Claim in retrieval? | **NO** (acceptance gate only) |
| Learn Scheduler connected? | **NO** |
| LanceDB live-verified? | **NO** (optional fail-open) |

---

## What Is Connected

```
local_heal
  -> MemoryRetrievalAdapter
  -> NexusCompositeLessonStore
  -> LocalJsonlLessonStore / FindingsMemoryStore / optional MemoryRepository
  -> native_evidence_packet
  -> ctx.op._memory_influence_trace
  -> receipt.memory_influence
  -> LearningClosureBridge
  -> JSONL + FindingsCard writeback
```

This is the **core memory lane**, not the full Nexus memory system.

---

## Recommendation

Proceed with memory relevance/ranking redesign on the connected core lane. Do not integrate MemPalace/Learn Scheduler until core ranking is validated.

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
