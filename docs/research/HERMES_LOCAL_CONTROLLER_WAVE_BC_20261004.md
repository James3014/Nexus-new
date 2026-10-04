# Hermes Local Controller Wave B-C — Integrated Continuation and Recovery

Date: 2026-10-04
Tracking: James3014/Nexus-new#1392
Predecessor: #1386 / PR #1387
Activation ceiling: bounded controller only; no daemon/24x7/merge/release/production authority

## Result

Wave B and Wave C are complete as a bounded, source-controlled controller.

The new `scripts/ops/nexus-hermes-continuation-controller` composes existing
authorities instead of replacing them:

```text
workflow doctor (read-only truth)
        |
        v
nexus-hermes-controller-guard
        |
        +-- WAIT/BLOCK/UNKNOWN -> stop
        +-- RECONCILE -> exact existing operation only
        +-- SAFE -> exact explicitly configured next-gate handler only
        |
        v
local Hermes / Qwen advisory
        |
        v
nexus-agy-dispatch (canonical effect owner)
```

Frontier escalation is a separate advisory-only command path and never receives
mutation authority.

## Crash-consistency contract

Before an external Agy dispatch, the controller persists an `effect_intent`
with a prompt digest and cwd. Only after the dispatcher returns a durable
`operation_id` is the intent bound to that identity.

If the controller restarts with an unbound intent, it returns:

`BLOCK_UNBOUND_EFFECT_INTENT`

and requires canonical operation-journal reconciliation before any retry.

This intentionally favors a false stop over a duplicate external effect.

## Wave B physical canary

Durable owner: Issue #1392

Initial doctor:
- disposition: `SAFE`
- next gate: `CONTINUE_BOUNDED_ISSUE_WORK`
- active operations: 0
- active leases: 0

Controller run:
- run_id: `wave-b-live`
- local model: Hermes -> Qwen3.6-35B-A3B-Splash
- effect intent persisted before dispatch
- Agy operation: `agyop_3cd245d2e31b487a9d7f2270003345f2`
- controller post-effect outcome: `EFFECT_STARTED_WAIT`

Terminal Agy readback:
- status: `COMPLETED`
- exit_code: 0
- stdout: `WAVE_B_AGY_CANARY_OK`
- tool_event_count: 0
- source_attribution_state: `ATTRIBUTED`
- base_head: `766556eb236f16f1c381aea6dd33deabdf31c5ad`

The same controller run was then restarted with the same run_id. It recovered
the persisted operation identity and effect count and returned
`EFFECT_BUDGET_EXHAUSTED`; no replacement operation was launched.

## Wave C recovery canaries

### WAIT

The Wave B effect was still active during mandatory post-effect doctor readback.
The controller stopped at `EFFECT_STARTED_WAIT` rather than dispatching again.

### Exact RECONCILE / no blind retry

Existing outcome-unknown specimen:
`agyop_971546858070446d863740713cffd79c`

Doctor:
- disposition: `RECONCILE`
- next gate: `RECONCILE_OPERATION`
- exact operation identity matched
- canonical status: `OUTCOME_UNKNOWN`

Controller:
- reconciled only the exact existing operation
- persisted the reconciliation receipt
- re-read doctor after reconciliation
- observed `RECONCILE` again
- returned `RECONCILED_STILL_UNKNOWN`
- did not create a replacement operation

The canonical reconciliation remains `retry_permitted=false`.

### Frontier adviser success

Deterministic escalation signal:
- same_gate_failures = 2
- evidence_conflict = true

Guard emitted:
- decision: `ASK_FRONTIER_ADVISER`
- authority: `ADVISORY_ONLY`

Physical transport:
- provider: GitHub Copilot
- model: GPT-4.1
- result: `FRONTIER_ADVICE_RECEIVED`

Advice:
`Read back the provider’s state for independent outcome evidence before any further action.`

The adviser had no mutation path.

### Frontier transport failure

The same deterministic escalation was executed with an intentionally invalid
model name.

Result:
- `FRONTIER_TRANSPORT_FAILED`
- controller exit: 7
- no fallback provider
- no mutation
- receipt authority remains `ADVISORY_ONLY`

### Controller lost-ack fence

A controller state was created with a persisted `effect_intent` but no
`operation_id`. The doctor, guard, Agy dispatcher, and Hermes binary paths
were all intentionally pointed to `/bin/false`.

The controller still stopped before invoking any of them:

- outcome: `BLOCK_UNBOUND_EFFECT_INTENT`
- action: `RECONCILE_CANONICAL_OPERATION_JOURNAL_BEFORE_ANY_RETRY`

This proves the replay fence is local controller state logic, not provider luck.

## Automated verification

Focused suite:
- `tests/ops/test_nexus_hermes_continuation_controller.py`
- `tests/ops/test_nexus_hermes_controller_guard.py`

Result:
- 20 tests passed
- Ruff check passed
- Ruff preview format check passed
- `git diff --check` passed

Covered behavior includes:
- observe-only mode
- WAIT stop
- BLOCKED stop
- unsupported next gate fail-closed
- intent-before-dispatch ordering
- unbound intent restart fence
- exact-operation reconciliation
- mismatched operation rejection
- persisted-operation restart
- deterministic frontier gating
- frontier transport failure without fallback
- post-effect doctor readback persisted in cycle receipt

## Authority and activation boundary

This controller does not:
- choose a worker/account outside canonical dispatch
- grant Agy leases
- accept a Candidate
- merge a PR
- deploy or release
- infer retry permission from timeout/process death
- install itself as a daemon
- become a second workflow truth store

Its local state is a crash/replay fence only. Canonical workflow/effect truth
remains in workflow doctor, GitHub, Nexus Core, and the Agy operation journal.

## Deferred to Wave D

The controller and guard are intentionally not yet added to the content-addressed
host-runtime manifest. Wave D should bind the merged exact source into a stable
runtime entrypoint before the multi-hour soak, then perform the 6-12 hour
wall-clock test. That is an activation/runtime qualification step, not part of
the bounded Wave B-C implementation.
