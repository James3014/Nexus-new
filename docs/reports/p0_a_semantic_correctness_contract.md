# P0-A: Semantic Correctness Contract

**Status**: P0_A_STATUS_PASS

## Files Changed

- `nexus/contracts/semantic_correctness_contract.py` (new)
- `tests/contracts/test_semantic_correctness_contract.py` (new)

## Commands Run

```bash
python3 -m py_compile nexus/contracts/semantic_correctness_contract.py  # OK
python3 -m pytest tests/contracts/test_semantic_correctness_contract.py -v  # 5/5 PASS
```

## Test Count

5 tests passing:
1. `test_semantic_correctness_assertion_frozen` — PASSED
2. `test_semantic_correctness_check_frozen` — PASSED
3. `test_compute_assertion_coverage_all_satisfied` — PASSED
4. `test_compute_assertion_coverage_no_assertions` — PASSED
5. `test_compute_assertion_coverage_partial` — PASSED

## Explicit Non-Goals

- Does NOT modify `completion_contract.py` (P0-B scope)
- Does NOT modify `isolated_verifier.py` (P0-C scope)
- Does NOT run model calls
- Does NOT run benchmarks

## Governance Boundary

`semantic_correctness_passed=False` does NOT yet cause `claim_eligible=False`. P0-B + P0-C are required to wire the field into the envelope and compute it from verifier output.
