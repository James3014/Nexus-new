# Task Card: lifecycle-workflow-p1c-receipt-failure-diagnostics

artifact_authority: current
owner: James Chen
status: COMPLETED_PENDING_OWNER_REVIEW
task_id: lifecycle-workflow-p1c-receipt-failure-diagnostics
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Add one additive, provider-neutral failure-diagnostics contract to the
UnifiedRuntime receipt. `failure_class` is the normalized terminal/closure
classification. `amplification_root_id` is a deterministic hash of the
normalized class, source stage, reason code, and provider identity; it excludes
task, attempt, timestamps, and raw error text so equivalent failures across
tasks can be grouped without becoming a second authority.

## Authority and boundaries

- UnifiedRuntime remains the receipt producer and terminal-state authority.
- The contract is additive and must not change receipt completion semantics,
  route selection, provider admission, retry, or claim authority.
- `public_claim_allowed` remains false.
- Success receipts use `failure_class: none` and an empty root id.
- Incomplete or blocked receipts use a non-empty class and `sha256:` root id.

## Allowed files

- `nexus/contracts/unified_runtime_receipt.py`
- `nexus/contracts/__init__.py`
- `nexus/services/unified_runtime.py`
- `tests/contracts/test_unified_runtime_receipt.py`
- `tests/services/test_unified_runtime.py`
- `tasks/lifecycle-agent-workflow-convergence/INDEX.md`
- `tasks/lifecycle-agent-workflow-convergence/01c-receipt-failure-diagnostics.md`

## Forbidden scope

- Do not alter `SKIPPED required capability` completion semantics.
- Do not add a second router, failure authority, database, or report.
- Do not change provider adapters or model workforce policy.
- Do not modify unrelated dirty files.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p1c-pycache uv run pytest -q tests/contracts/test_unified_runtime_receipt.py tests/services/test_unified_runtime.py
git diff --check
```

## Exit criteria

- Every UnifiedRuntime receipt path contains the two top-level fields and the
  nested `failure_diagnostics` object.
- Equivalent normalized failures share an `amplification_root_id`; task and
  attempt changes do not change it.
- Success remains `receipt_complete`/claim semantics identical to baseline.
- Contract validator fails closed on malformed or mismatched diagnostics.

## Verified evidence

- `tests/contracts/test_unified_runtime_receipt.py` plus
  `tests/services/test_unified_runtime.py`: `144 passed`.
- Revision-bound fresh-suite manifest at
  `/tmp/nexus-fresh-suite-1fa8062c.json`: `PASS`, 5 passed, 0 failed, 0 skipped,
  clean HEAD `1fa8062c79ad48ae499020c37a979902a2d19b5f`.
- Six-control manifest at `/tmp/nexus-control-gate-1fa8062c.json`: `PASS`,
  6 passed, 0 failed, 0 skipped, clean checkout.
- Equivalent normalized provider failures share a root id while task and
  attempt identity remain excluded from the root hash.

## Block classification

- `RECOVERABLE_BLOCK`: focused test or local tooling failure.
- `HARD_BLOCK`: request to widen authority, alter completion semantics, or
  introduce a parallel taxonomy.
