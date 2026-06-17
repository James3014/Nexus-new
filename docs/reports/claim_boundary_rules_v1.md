# Claim Boundary Rules v1

## Overview

All new report/receipt summaries must include claim boundary fields. These rules determine whether a result can be used for public claims.

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `simulated` | bool | Whether this result was simulated (not a real run) |
| `claim_eligible` | bool | Whether this result qualifies for claim |
| `receipt_present` | bool | Whether an abort/completion receipt exists |
| `model_calls` | int | Number of model invocations |
| `visible_tests_passed` | int | Number of visible tests passed |
| `hidden_tests_passed` | int | Number of hidden tests passed |
| `public_claim_allowed` | bool | Whether public claim is permitted |
| `claim_block_reason` | str | Semicolon-separated reasons if blocked |

## Rules

1. **simulated=true → public_claim_allowed=false**
   Simulated data cannot be used for public claims.

2. **receipt_present=false → public_claim_allowed=false**
   No receipt means no audit trail. Claim not permitted.

3. **claim_eligible=false → public_claim_allowed=false**
   Result marked ineligible. Claim not permitted.

4. **model_calls=0 → public_claim_allowed=false**
   No model invocations means no model capability claim.

5. **workspace_provisioning_failure → not counted as patcher failure**
   Workspace failures are infrastructure issues, not patcher logic failures.

## Usage

```python
from nexus.evidence.claim_boundary import evaluate_claim_boundary

boundary = evaluate_claim_boundary(
    simulated=False,
    claim_eligible=True,
    receipt_present=True,
    model_calls=3,
    visible_tests_passed=5,
    hidden_tests_passed=2,
)
assert boundary.public_claim_allowed is True
```

## Integration Points

- `AbortReceipt` includes `receipt_present`, `claim_eligible`, `simulated`, `model_calls`
- `DedupeManifest` ensures alias deduplication before claim evaluation
- All new receipts must call `evaluate()` before allowing public claims
