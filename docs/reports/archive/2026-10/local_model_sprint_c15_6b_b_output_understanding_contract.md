# C15-6B-B: Output Understanding Contract for Committee Candidates

**Date**: 2026-07-04  
**Status**: `FOCUSED_CONTRACT_PROVEN`

## 1. Task

```text
Introduce a minimal generalized output-understanding contract so committee
candidates are represented as understanding results, not only raw patch-format
telemetry.
```

## 2. Changes

Files changed:

```text
nexus/services/local_heal/output_understanding.py
nexus/services/local_heal/committee_orchestrator.py
tests/unit/local_heal/test_output_understanding.py
tests/unit/local_heal/test_committee_route_trace.py
```

New contracts:

```text
- CanonicalPatchCandidate
- OutputUnderstandingResult
```

Committee candidate trace now includes:

```text
- source_format
- normalization_steps
- anchor_status
- output_understanding
```

## 3. Scope

This is a contract and observability step only.

It does:

```text
- convert existing patch-phase truth into a generalized understanding result
- attach candidate-level normalization and anchor metadata to committee trace
- preserve compatibility with existing committee trace fields
```

It does not:

```text
- change planner authority
- change verifier authority
- claim full canonical candidate rollout across all paths
- prove live 2-model or 3-model solve success
```

## 4. Verification

Commands:

```bash
python3 -m py_compile \
  nexus/services/local_heal/output_understanding.py \
  nexus/services/local_heal/committee_orchestrator.py \
  tests/unit/local_heal/test_output_understanding.py \
  tests/unit/local_heal/test_committee_route_trace.py
```

```bash
uv run pytest \
  tests/unit/local_heal/test_output_understanding.py \
  tests/unit/local_heal/test_committee_route_trace.py \
  -q
```

Observed result:

```text
21 passed in 0.48s
```

## 5. Gate Impact

This advances C15-6B Phase 2 by proving:

```text
- committee candidates now have a formal understanding contract
- normalization truth is inspectable per candidate
- receipt persistence still works after the contract addition
```

Still not proven:

```text
- live dual-model validation gate
- live triple-model validation gate
- solve-claim gate on a real task
```
