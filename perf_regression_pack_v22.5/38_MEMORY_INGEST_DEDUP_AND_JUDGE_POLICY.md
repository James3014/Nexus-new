# 38_MEMORY_INGEST_DEDUP_AND_JUDGE_POLICY.md

**Purpose**: Eligibility and Deduplication for findings entering Core Memory.
**Source**: memory_repository.py (Ref), Trace-Dedup (Ref)
**Commit**: v23.5-alpha-spec-038
**Generated_at**: 2026-04-08 07:21

---

## 🏗️ Deduplication Engine
`Semantic Distance < 0.1`: Auto-discard (Logged).
`Distance 0.1 - 0.3`: Merge.
`Distance > 0.3`: New memory.
