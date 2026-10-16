# P11: Rerun Hard Tasks After P9/P10 Report

## Phase Summary

| Field | Value |
|-------|-------|
| Phase | P11 |
| Commit SHA | d9b62b10 |
| Status | P11_READY_FOR_EXECUTION |
| Files Changed | 1 new script |
| Tests Run | 224 (all passing) |
| Script | `scratch/run_p11_hard_tasks.py` |

## Infrastructure Changes Applied

### P9 Integration
- Anchor extraction enforced AFTER base_commit checkout
- Source hash computed from checked-out source
- Anchor text hash verified for integrity
- Strict replacement parser rejects prose/markdown contamination

### P10 Integration
- Semantic anchor selection generates multiple candidates
- Candidates scored on 5 dimensions (behavior, trace, span, keywords, leaf)
- Best candidate selected automatically
- Fallback to hardcoded anchor if selection fails

## Task Status (Pre-Execution)

| Task | Instance | Status | Notes |
|------|----------|--------|-------|
| C_11618 | sympy__sympy-11618 | READY | Anchor provenance enforced |
| C_12481 | sympy__sympy-12481 | READY | Strict parser will reject prose |
| C_13453 | astropy__astropy-13453 | READY | Semantic selection available |

## Expected Improvements

### C_11618 (Point.distance dimension check)
- **P5**: Anchor was correct but extraction order may have been wrong
- **P11**: Anchor extraction now guaranteed after checkout
- **Expected**: Should no longer fail with ANCHOR_NOT_IN_SOURCE

### C_12481 (Permutation non-disjoint cycles)
- **P5**: Parser may have accepted prose-contaminated output
- **P11**: Strict parser rejects prose, markdown fences, bullet lists
- **Expected**: Should no longer accept prose as code

### C_13453 (HTML writer formats parameter)
- **P5**: Anchor was at wrong semantic layer (iter_str_vals call site)
- **P11**: Semantic selection may find better anchor (formatting behavior)
- **Expected**: May select anchor closer to the actual formatting logic

## Execution Instructions

To run P11:

```bash
# Ensure Ollama is running with the model
ollama pull gemma4-coder-12b-q4km:latest

# Run the script
uv run scratch/run_p11_hard_tasks.py
```

## Comparison Table (Post-Execution)

| Metric | C4 Baseline | P5 Result | P11 Result |
|--------|-------------|-----------|------------|
| SEARCH_MISMATCH | 3/3 (100%) | 0/9 (0%) | (pending) |
| ANCHOR_NOT_IN_SOURCE | 1/3 | 0/3 | (pending) |
| Prose contamination | 1/3 | 0/3 | (pending) |
| Patch apply success | 0/3 | 7/9 | (pending) |
| Verifier pass | 0/3 | 0/3 | (pending) |

## Proceed to P12

P11 script is ready for execution. Proceed to P12 for capability delta analysis after execution.
