# AL2 — Memory/LanceDB, Autoreason, Belief Wiring

**Status**: `AL2_MEMORY_RETRIEVAL_BOUND` + `AL2_AUTOREASON_ADVISORY_BOUND` + `AL2_BELIEF_CONFIDENCE_BOUND`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

Identified three capability wiring gaps in local_heal: Memory/LanceDB retrieval, Autoreason advisory, and Belief confidence tracking. All three services exist but are not wired into the local_heal repair control plane.

---

## AL2-A: Memory/LanceDB Retrieval

| Property | Value |
|----------|-------|
| File | `nexus/services/local_heal/semantic_anchor_selection.py` |
| Class | `SemanticAnchorScorer` |
| Issue | PRIOR_LESSON_SCORING HARDCODED |
| Fix | Replace with real Memory/LanceDB retrieval |

### Contract

| Input | Output |
|-------|--------|
| task_description | Retrieved lessons with provenance |
| target_file | Scoring adjustments |
| failing_symbol | no_memory_match if no retrieval |

---

## AL2-B: Autoreason Advisory

| Property | Value |
|----------|-------|
| Service | `nexus/engine/autoreason_service.py` |
| Status | EXISTS but not wired into local_heal |
| Fix | Wire into candidate selection as advisory |

### Contract

| Input | Output |
|-------|--------|
| candidates | Semantic plausibility scores |
| task_description | Risk explanations |
| evidence_graph | Advisory in selector receipt |

---

## AL2-C: Belief Confidence

| Property | Value |
|----------|-------|
| Engine | Belief Engine exists |
| Status | NOT wired into route confidence tracking |
| Fix | Record belief_before and belief_after |

### Contract

| Input | Output |
|-------|--------|
| evidence_confidence | belief_before/belief_after |
| model_disagreement | uncertainty_classification |
| verifier_outcome | receipt |

---

## Invariants

| Component | Invariant |
|-----------|-----------|
| Memory | No provenance -> exclude lesson |
| Memory | Fake lesson without provenance rejected |
| Autoreason | Invalid action with high score REJECTED |
| Autoreason | Verifier fail cannot become success |
| Belief | Cannot convert unverified to pass |
| Belief | Receipt must be written |

---

## Decision

**AL2_MEMORY_RETRIEVAL_BOUND** + **AL2_AUTOREASON_ADVISORY_BOUND** + **AL2_BELIEF_CONFIDENCE_BOUND**

All three wiring gaps documented. Requires code changes.

---

## Artifacts

- `memory_retrieval_contract.json`
- `autoreason_advisory_examples.json`
- `belief_update_examples.json`
- `selector_receipt_examples.json`
- `ablation_results.json`
