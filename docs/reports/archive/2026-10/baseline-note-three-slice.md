# Nexus Baseline Note — Three-Slice Capability Uplift

**Date**: 2026-06-15
**Baseline Commit**: `0a673f3e`

---

## Slice A: PACT for 3B Advisor

### Current State
- `S2T3BAdvisor.advise()` returns JSON dict:
  ```json
  {
    "selected_candidate_id": "A",
    "selection_reason_codes": ["matches_route_decision"],
    "required_verifier": null,
    "abstain_reason": ""
  }
  ```
- `OracleAdvisor.synthesize_advice()` returns free-form text (not structured)
- `s2t_export.py` has structured training export (v2/v3)

### Token Length (estimated)
- Advisor output: ~100-200 tokens (JSON)
- OracleAdvisor output: ~300-500 tokens (free-form)

### Risk Level
- Low: advisor output only affects candidate ranking, not final decision

---

## Slice B: Skill Memory Query Layer

### Current State
- `skill_outcomes.py`: `OutcomePayload` dataclass, `append_skill_outcome_event()`
- `skill_lifecycle.py`: `UsageEvent` dataclass, `record_usage()`
- Storage: `.nexus/metrics/skill_outcome_events.jsonl`
- No unified query layer exists

### Data Sources
1. Skill outcome events (JSONL)
2. Usage logs (JSONL)
3. Skill lifecycle (trust levels, promotion)

### Risk Level
- Low: query layer only reads, doesn't write

---

## Slice C: SWE-Explore Lite

### Current State
- `vector_rag.py`: LanceDB vector search with Ollama embeddings
- `localizer.py`: BM25 + AST-based file ranking and code extraction
- `granular_localizer.py`: Advanced surgical slicing with call graph

### Retrieval Granularity
- File-level: BM25 scoring (localizer.py)
- Function-level: AST parsing (granular_localizer.py)
- Line-level: Not implemented (currently file-level only)

### Risk Level
- Low: retrieval improvements only affect input to patch synthesis

---

## Feature Flags (all OFF by default)
- `NEXUS_S2T_PACT_ENABLED`
- `NEXUS_S2T_SKILL_MEMORY_ENABLED`
- `NEXUS_RETRIEVAL_MULTIGRANULARITY_ENABLED`

---

## Test Coverage
- Slice A: `tests/gates/test_s2t_claim_gate.py` (31 tests)
- Slice B: No existing tests
- Slice C: No existing tests

---

## Execution Order
1. Phase 0: Baseline Freeze ✅
2. Phase 1: Slice A (PACT)
3. Phase 2: Slice B (Skill Memory Query)
4. Phase 3: Slice C (SWE-Explore Lite)
5. Phase 4: Integrated Replay
