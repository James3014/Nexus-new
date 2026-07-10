# N30R-V1 Known Baseline Regressions

**Recorded at**: V1 baseline 958b915f2

## Suite: tests/engine/test_capability_routing_contracts.py

**Result**: 30 passed / 2 failed

### Failure 1

```text
test_core_gate_receipts_require_specific_evidence_before_public_claim
```

Actual failure reason: `missing_verifier_artifact;missing_source_hash`
Expected: `invoked_without_evidence`

### Failure 2

```text
test_core_gate_failed_receipts_count_as_fail_closed_outcomes_not_public_safe
```

Actual failure reason: `missing_verifier_artifact;missing_source_hash`
Expected: `evidence_without_gate_pass`

## Classification

```text
PRE_EXISTING_AT_V1_BASELINE
NOT_INTRODUCED_BY_W1C2
OUTSIDE_V1_VERTICAL_SLICE_SCOPE
```

## Evidence

- W1C2 did not modify `nexus/engine/capability_receipts.py`
- W1C2 did not modify `nexus/engine/capability_receipt_adapters.py`
- W1C2 did not modify `tests/engine/test_capability_routing_contracts.py`
- Failures reproduce on baseline commit 958b915f2 (verified by git stash)
- Root cause: `ClaimGateReceiptAdapter` and `DeliveryGateReceiptAdapter` require `verifier_artifact`/`verifier_status` and `source_hash` fields that the test payloads do not provide
- This is correct production behavior (stricter evidence requirements), not a regression

## Impact on V1

Does not block V1 vertical slice. The V1 slice tests different capabilities (projection, evidence wiring, prompt capture, candidate lifecycle, verifier, retry) through `n30r_real_core_bridge.py` and `local_model_executor.py`, not through `build_trace_receipts()`.
