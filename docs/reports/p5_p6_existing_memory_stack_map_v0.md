# P5/P6 Existing Memory Stack Map

## Purpose

Inventory existing Nexus memory/learning/retrieval/policy capabilities. P5/P6/M1 must consume existing substrate, NOT build parallel memory stack.

## Capabilities Inventory

### 1. FindingsMemoryStore
- **File**: `nexus/research/findings_memory.py`
- **Public**: `FindingsMemoryStore` class
- **Current callers**: Research learn/ingest/claim services
- **P5/P6 role**: `consume` — long-term memory store for research findings
- **Do-not-duplicate**: Yes — this is the canonical findings store

### 2. MemoryRetrievalAdapter
- **File**: `nexus/services/local_heal/memory_retrieval_adapter.py`
- **Public**: `MemoryRetrievalAdapter` class
- **Current callers**: local_model_executor.py (memory capability)
- **P5/P6 role**: `consume` — retrieval path for local heal
- **Do-not-duplicate**: Yes — this is the canonical retrieval adapter

### 3. LocalJsonlLessonStore
- **File**: `nexus/core/retrieval_memory_adapter.py`
- **Public**: `LocalJsonlLessonStore` class
- **Current callers**: MemoryRetrievalAdapter
- **P5/P6 role**: `consume` — local JSONL-based lesson storage
- **Do-not-duplicate**: Yes — already used by retrieval adapter

### 4. MemoryRepositoryLessonStore
- **File**: `nexus/core/retrieval_memory_adapter.py`
- **Public**: `MemoryRepositoryLessonStore` class
- **Current callers**: MemoryRetrievalAdapter
- **P5/P6 role**: `consume` — repository-based lesson storage
- **Do-not-duplicate**: Yes — already used by retrieval adapter

### 5. NexusCompositeLessonStore
- **File**: `nexus/core/retrieval_memory_adapter.py`
- **Public**: `NexusCompositeLessonStore` class
- **Current callers**: MemoryRetrievalAdapter
- **P5/P6 role**: `consume` — composite store combining local + repository
- **Do-not-duplicate**: Yes — already used by retrieval adapter

### 6. MemoryTrace
- **File**: `nexus/services/local_heal/memory_trace.py`
- **Public**: `MemoryTrace` class, `get_empty_trace()`
- **Current callers**: receipt.py, orchestrator.py
- **P5/P6 role**: `consume` — receipt path for memory traces
- **Do-not-duplicate**: Yes — this is the canonical receipt path

### 7. shadow_memory_ranking
- **File**: `nexus/services/local_heal/shadow_memory_ranking.py`
- **Public**: `shadow_memory_ranking()` function
- **Current callers**: memory_retrieval_adapter.py
- **P5/P6 role**: `extend-with-telemetry` — where copyability/usefulness telemetry attaches
- **Do-not-duplicate**: Yes — extend existing ranking, don't rebuild

### 8. lesson_retrieval / LanceDB hybrid
- **File**: `nexus/services/lesson_retrieval.py`
- **Public**: `lesson_retrieval()` function
- **Current callers**: memory_retrieval_adapter.py
- **P5/P6 role**: `consume` — LanceDB-based lesson retrieval
- **Do-not-duplicate**: Yes — already used by retrieval adapter

### 9. Learning Closure
- **File**: `.nexus/reports/learn/` (JSONL files)
- **Public**: JSONL lesson storage
- **Current callers**: orchestrator.py (learning closure)
- **P5/P6 role**: `consume` — long-term memory/writeback
- **Do-not-duplicate**: Yes — this is the canonical lesson store

### 10. policy_memory
- **File**: `.nexus/knowledge/policy_memory.jsonl`
- **Public**: JSONL policy storage
- **Current callers**: policy_gate.py
- **P5/P6 role**: `consume` — policy memory for decision gate
- **Do-not-duplicate**: Yes — this is the canonical policy store

### 11. MemPalace
- **File**: `nexus/core/mem_palace.py`
- **Public**: `MemPalace` class
- **Current callers**: orchestrator.py, local_model_executor.py
- **P5/P6 role**: `consume` — decides whether memory influences decisions
- **Do-not-duplicate**: Yes — this is the canonical memory influence gate

### 12. policy_gate
- **File**: `nexus/services/policy_gate.py`
- **Public**: `policy_gate()` function
- **Current callers**: orchestrator.py
- **P5/P6 role**: `consume` — decides whether policy influences decisions
- **Do-not-duplicate**: Yes — this is the canonical policy gate

### 13. BeliefEngine
- **File**: `nexus/core/belief_engine.py`
- **Public**: `BeliefEngine` class
- **Current callers**: orchestrator.py
- **P5/P6 role**: `consume` — read-only until proven
- **Do-not-duplicate**: Yes — this is the canonical belief engine

### 14. p5_selection_memory.py
- **File**: `nexus/services/local_heal/p5_selection_memory.py`
- **Public**: `create_selection_memory_action()`, `read_and_mark_used()`
- **Current callers**: test only
- **P5/P6 role**: `bridge-to` — bridge candidate, NOT long-term store
- **Do-not-duplicate**: Yes — this is a bridge, not a store

## Key Relationships

```
FindingsMemoryStore (long-term write)
    ↓
MemoryRetrievalAdapter (retrieval)
    ↓
LocalJsonlLessonStore / MemoryRepositoryLessonStore / NexusCompositeLessonStore (storage)
    ↓
shadow_memory_ranking (ranking + telemetry)
    ↓
lesson_retrieval / LanceDB (hybrid retrieval)
    ↓
Learning Closure (.nexus/reports/learn/) (writeback)
    ↓
policy_memory (.nexus/knowledge/policy_memory.jsonl) (policy)
    ↓
MemPalace / policy_gate (decision influence)
    ↓
BeliefEngine (read-only)
```

## P5/P6 Integration Points

- **P5 selection**: Consume `shadow_memory_ranking` for copyability/usefulness telemetry
- **P5 memory**: `p5_selection_memory.py` bridges selection → memory append
- **P6 quota**: Read from `policy_memory` for degradation decisions
- **P6 context**: Read from `MemPalace` for memory influence context

## Explicit Statements

- EffectLedger is NOT a memory store — it is an evaluation artifact under artifacts/
- p5_selection_memory.py is a bridge candidate, NOT a long-term store
- MemoryTrace is the receipt path
- MemoryRetrievalAdapter is the retrieval path
- FindingsMemoryStore / Learning Closure are long-term memory/writeback
- shadow_memory_ranking is where copyability/usefulness telemetry attaches
- MemPalace / policy_gate decide whether memory influences decisions
- Belief signal is read-only until proven
