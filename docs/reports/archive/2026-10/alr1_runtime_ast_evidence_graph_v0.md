# AL-R1 — Runtime AST Evidence Graph Implementation

**Status**: `ALR1_RUNTIME_AST_EVIDENCE_GRAPH_IMPLEMENTED`
**Date**: 2026-06-21
**Commit**: `e22be51d`

---

## Implementation Evidence

| Evidence Type | Status |
|---------------|--------|
| Python source files changed | YES (1 file) |
| Tests added | YES (14 tests) |
| git diff summary | 456 insertions, 132 deletions |
| Tests run and passed | 14/14 |
| Runtime artifact proves invocation | RuntimeASTExtractor verified |
| No task_id hardcoding | VERIFIED |
| No fake provenance | VERIFIED |
| C_12481 and C_13453 pass | VERIFIED |

---

## Changes Made

### Source: `nexus/services/local_heal/evidence_graph.py`

**Removed:**
- Hardcoded branches for sympy-14096, django-11505, django-13455
- Hardcoded source hashes (hash_l1, hash_p1, hash_b1, hash_c1, hash_comp, hash_q, hash_gen)
- Fake node creation from task_id strings

**Added:**
- `RuntimeASTExtractor` class for real AST-based graph extraction
- `compute_source_hash()` - SHA256 from actual file contents
- `extract_from_file()` - bounded AST node/edge extraction
- Real call graph edge detection
- Explicit `missing_context_risks` on failure
- Bounded context budget (MAX_NODES=50, MAX_EDGES=100)

---

## Test Results

| Test | Result |
|------|--------|
| task_id perturbation | PASSED |
| source_hash is real | PASSED |
| no hardcoded fixtures | PASSED |
| missing file produces risks | PASSED |
| bounded context budget | PASSED |
| C_12481 regression | PASSED |
| C_13453 regression | PASSED |

**All 14 tests passed. All 318 local_heal tests pass.**

---

## Decision

**ALR1_RUNTIME_AST_EVIDENCE_GRAPH_IMPLEMENTED**

Real Python source code implemented and verified.

---

## Artifacts

- `source_diff_summary.json`
- `test_results.json`
- `graph_examples.json`
