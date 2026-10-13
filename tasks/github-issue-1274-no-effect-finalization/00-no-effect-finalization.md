# Issue 1274 — Bounded Source No-Effect Reconciliation and Process Consistency

- task_id: `github-issue-1274-no-effect-finalization`
- campaign_id: `github-issue-1274-no-effect-finalization`
- status: `CANDIDATE`
- owner: `James Chen (James3014)`
- coordinator: `Antigravity Engineer`
- issue: `https://github.com/James3014/Nexus-new/issues/1274`
- durable_marker: `SOURCE_NO_DURABLE_EFFECT_PROVEN`
- AUTO_CHAIN: `false`

## Objective

Establish a bounded, fail-closed reconciliation mechanism (`--finalize-no-effect <operation_id>`) for `OUTCOME_UNKNOWN` Agy operations where:
1. The process truth is bounded and confirmed terminal (`pid_alive == False`, `provider_alive_after == False`).
2. The account lease cleanup is confirmed safe (`ALREADY_ABSENT` or `LEASE_RECEIPT_REMOVED`).
3. The captured source repository root and base HEAD match the current git state.
4. The captured source baseline hash remains valid and matches.
5. The repository source state is verified unchanged (`observed_changed_paths == []` and `first_effect_at is None`).

When these conditions are proven, the operation converges deterministically out of `OUTCOME_UNKNOWN` into `FAILED` with `reconciliation.result = "SOURCE_NO_DURABLE_EFFECT_PROVEN"`, `reconciliation_scope = "SOURCE_ONLY"`, and `retry_permitted = True`. Missing, altered, dirty, or unverified evidence fails closed and preserves `OUTCOME_UNKNOWN`.

## Allowed Files

- `nexus/services/direct_operation_journal.py`
- `scripts/ops/nexus-agy-dispatch`
- `tests/services/test_agy_dispatch.py`
- `tests/services/test_agy_operation_journal.py`
- `tests/services/test_workflow_doctor.py`
- `tasks/github-issue-1274-no-effect-finalization/00-no-effect-finalization.md`
- `tasks/github-issue-1274-no-effect-finalization/INDEX.md`

## Acceptance Criteria

1. Bounded prove method `prove_source_state_unchanged(operation_id)` in `DirectOperationJournal` asserts that source attribution is available, no effect occurred, and working tree matches baseline hash and base HEAD.
2. CLI and dispatcher function `_finalize_no_effect_operation` reconciles process and lease state before checking source proof.
3. Successfully finalized operation transitions from `OUTCOME_UNKNOWN` to `FAILED` with `reconciliation.result = "SOURCE_NO_DURABLE_EFFECT_PROVEN"` and `retry_permitted = True`.
4. Idempotent re-execution of `--finalize-no-effect` returns the exact existing receipt.
5. Fails closed with explicit errors on dirty working tree, head changes, unverified processes, or conflicting lease identities.
6. Doctor recognizes `SOURCE_NO_DURABLE_EFFECT_PROVEN` as a reconciled non-running state and does not trigger `RECONCILE_OPERATION`.
7. Zero deletions to unrelated files (`model_capability_lineage.yaml` or other models).
8. All unit tests pass, `ruff check` passes, `ruff format --check --preview` passes, and `git diff --check` passes.

## Claim Ceiling

Source candidate and verified test suite only. No merge, runtime activation, or release authority.
