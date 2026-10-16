# C15-6B-A: Committee Execution Truth Fields

**Date**: 2026-07-04  
**Status**: `FOCUSED_WIRING_EVIDENCE_PROVEN`

## 1. Task

```text
Strengthen committee trace truth so dual-model and triple-model validation can
prove real proposer execution rather than only candidate labels.
```

## 2. Changes

Files changed:

```text
nexus/services/local_heal/committee_orchestrator.py
tests/unit/local_heal/test_committee_route_trace.py
```

Added per-candidate truth fields:

```text
- expected_model
- invoked_model
- output_class
- parser_error_kind
- conversion_status
- source_format
```

## 3. Why

Previous committee trace already preserved:

```text
- candidate_id
- model
- role
- selected/applied/worktree_applied
- selected/applied hash truth
```

But it did not expose enough candidate-level runtime truth to gate:

```text
- expected proposer model vs invoked model
- whether the candidate came from search/replace vs unified diff vs empty output
- whether unified diff conversion happened
- whether parser failure was candidate-specific
```

Without these fields, 2-model / 3-model validation could still over-rely on
labels instead of observable execution truth.
```

## 4. Verification

Commands:

```bash
python3 -m py_compile \
  nexus/services/local_heal/committee_orchestrator.py \
  tests/unit/local_heal/test_committee_route_trace.py
```

```bash
uv run pytest tests/unit/local_heal/test_committee_route_trace.py -q
```

Observed result:

```text
19 passed in 0.48s
```

## 5. Gate Impact

This clears part of C15-6B Phase 1:

```text
- per-candidate proposer execution truth is now explicit in committee trace
- output understanding evidence is now externally inspectable at candidate level
```

Still not proven:

```text
- true 3-model live execution in current runtime
- full canonical candidate layer
- committee solve claim on a real task
```
