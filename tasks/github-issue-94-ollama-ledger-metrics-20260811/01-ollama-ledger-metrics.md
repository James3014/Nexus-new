---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-94-ollama-ledger-metrics
campaign_id: github-issue-94-ollama-ledger-metrics-20260811
source_issue: https://github.com/James3014/Nexus-new/issues/94
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
---

# Additive Ollama metrics persistence

## Allowed files

- `nexus/services/local_heal/local_model_provider.py`
- `tests/unit/local_heal/test_local_model_provider.py`
- this card and `INDEX.md`

## Objective

Copy the current Ollama response metrics already observed at provider-call
time into `LedgerRecord` and its `to_dict()` output. Missing metrics remain
explicitly `None`/absent according to the existing response contract; no zero
fabrication or correctness/promotion claims are permitted.

## Forbidden scope

- provider/model selection, routing, workforce, runtime, lifecycle, approval,
  integration, release, or production changes
- PR #143 and unrelated router/runtime files
- changing provider success/error semantics

## Verification and claim ceiling

Run focused local-model provider tests, Ruff check/preview, compileall, and
`git diff --check`. Terminal marker: `OLLAMA_LEDGER_METRICS_PERSISTED`.
Maximum claim: `OLLAMA_LEDGER_METRICS_PERSISTED` (source-tested additive
ledger persistence only).
