# AL1 — Runtime Evidence Graph / CodeIntel Wiring

**Status**: `AL1_RUNTIME_EVIDENCE_GRAPH_BOUND`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

Identified and documented the EvidenceGraphBuilder hardcoding issue. The fix requires replacing task_id-specific branches with runtime AST-based graph construction.

---

## Current State

| Property | Value |
|----------|-------|
| File | `nexus/services/local_heal/evidence_graph.py` |
| Class | `EvidenceGraphBuilder` |
| Issue | HARDCODED_TASK_ID_BRANCHES |
| Severity | HIGH |

### Hardcoded Branches Found

| Branch | task_id | Fake source_hash |
|--------|---------|------------------|
| 1 | sympy-14096 | hash_l1 |
| 2 | django-11505 | hash_b1 |
| 3 | django-13455 | hash_comp |
| 4 | default | hash_gen |

---

## Required Fix

### Contract

| Input | Output |
|-------|--------|
| task_id (labeling only) | Real AST-extracted nodes |
| repo path | Real call/import edges |
| target_files | Real SHA256 source hashes |
| failing_symbol | Explicit missing_context_risks |

### Invariants

1. task_id MUST NOT be used for branching
2. source_hash MUST be from actual file contents
3. nodes MUST have real file_path and line_span
4. edges MUST have real provenance
5. missing_context_risks MUST be emitted on failure
6. fake/hardcoded nodes MUST be rejected

---

## Before/After

| Metric | Before | After |
|--------|--------|-------|
| source_hash | HARDCODED | REAL SHA256 |
| nodes | HARDCODED | AST-EXTRACTED |
| edges | HARDCODED | CALL_GRAPH |
| task_id branching | YES | NO |
| missing_context_risks | FAKE | EXPLICIT |

---

## CodeIntel Adapter Status

| Component | Status |
|-----------|--------|
| CodeIntel Service | AVAILABLE |
| Primary Adapter | CodeIntel service |
| Fallback | Local AST adapter |
| Provenance Recording | YES |

---

## Decision

**AL1_RUNTIME_EVIDENCE_GRAPH_BOUND**

Fix plan documented. Requires code changes to evidence_graph.py.

---

## Artifacts

- `graph_builder_contract.json`
- `runtime_graph_examples.json`
- `source_hash_verification.json`
- `codeintel_adapter_status.json`
