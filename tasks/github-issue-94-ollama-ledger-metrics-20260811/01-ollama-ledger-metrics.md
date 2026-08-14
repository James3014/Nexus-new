---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: github-issue-94-ollama-ledger-metrics
campaign_id: github-issue-94-ollama-ledger-metrics-20260811
issue: 94
repository: James3014/Nexus-new
source_issue: https://github.com/James3014/Nexus-new/issues/94
baseline_revision: 8e05e0827fe913e3e408f87dc274e005bdc0bf92
reconciled_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
current_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
terminal_marker: OLLAMA_LEDGER_METRICS_PERSISTED
claim_ceiling: OLLAMA_LEDGER_METRICS_PERSISTED
implementation_gate: SATISFIED_BY_PR158_MERGE_19343D31
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

## Terminal Reconciliation

This card is complete at the bounded additive ledger-persistence ceiling.
Historical implementation frontmatter (`status: ACTIVE`,
`worker_may_commit/push: true`) describes the superseded implementation phase
of PR #158 and is preserved as historical narrative only. PR #158 exact head
`a893fc774c4c18b33b1c08f1b6c5fadac57a3aa7` merged as
`19343d31be9d5a7f53cfb568ceca405d473d99a5` from exact base
`8e05e0827fe913e3e408f87dc274e005bdc0bf92`; independent receipt `4908555861`
recorded MERGE_SAFE, 21 focused tests passed, Tier3 skipped, exact four-file
scope with zero deletions. Current `main` retains the implementation source
and focused tests.

This terminal status grants no provider runtime call, routing, Workforce,
approval, integration, merge, release, or production authority. No deletion or
product/test change is part of this reconciliation.
