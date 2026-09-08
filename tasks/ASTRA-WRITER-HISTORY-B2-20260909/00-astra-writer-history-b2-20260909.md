# Task Card: astra-writer-history-b2-20260909

artifact_authority: current
task_id: `astra-writer-history-b2-20260909`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Bounded correction to the previously approved B writer registry path required by the original F restart/reacquisition acceptance. Add WriterRegistry.reconcile_terminal_history(coordinator) using the fixed source-owned F verify_loaded_cohort_terminal_history(registry, coordinator) verifier; require exact actual registered F coordinator, current registry/held root/vector/process/CAS, immutable original typed DRAINED receipt and lease-vector bytes, terminal committed/failed outcomes, and verified original producer absence. Store per-registry exact original admission path and raw SHA256 pins. In _durable_leases suppress only the foreign-process issue for an exact unchanged pinned terminal record; malformed, unresolved, changed, absent, unbound, live/unknown producer and forged coordinator remain denied. Preserve original ledger paths/bytes and acquire duplicate-operation fences: no archive, move, rewrite, delete, identity rebadging, broad foreign-process suppression, or monkeypatch. Every new process must requalify. F verifier and integration tests are owned by the existing F card in staging; this B2 card owns only the B correction and never claims F accepted. Baseline is E accepted source plus F formal card 2205d9b6cf0a71028ab07a4602708dbabff26caa, tree e924029cdcaffa008b2f2e66b6226c14cfce89f3. Independent combined B2/F verification must cover pre-hold actual writes, restart/new writes, replayed old operation denial, exact historical tamper/unresolved denial and all crash boundaries. Worker may commit an exact scoped source Candidate after parent diff review; commit is not acceptance. No provider/API-key/SDK/Agy/Gemini/native/network, live authority, deployment, main push/merge, approval/integration/retirement/production action. AUTO_CHAIN=false.

## Allowed files

- `nexus/orchestrator/writer_quiescence.py`

## Verification commands

```bash
python3 -B -m pytest -q tests/nexus/orchestrator/test_writer_quiescence.py
python3 -B -m py_compile nexus/orchestrator/writer_quiescence.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
