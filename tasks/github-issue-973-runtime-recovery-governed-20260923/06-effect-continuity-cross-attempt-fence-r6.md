# ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R6 — Effect continuity cross-attempt fence repair

This Card is the bounded governed successor to the superseded R5 adoption contract for Issue #973.
It preserves the two previously closed High findings and adds the missing cross-attempt unresolved-effect
fence required by the latest PRE_EFFECT_AUTHORITY / EFFECT_CONTINUITY contract refinement.

It does **not** authorize live runtime recovery, Gateway deployment, release, production claims, or
reuse of the old immutable R5 Candidate.

- **Campaign:** `github-issue-973-runtime-recovery-governed-20260923`
- **Task ID:** `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R6`
- **Attempt ID:** new attempt identity required at execution time
- **Status:** `ACTIVE_AFTER_TRACKING`
- **Issue:** `973`
- **Execution lane:** `GOVERNED`
- **Auto-chain:** `false`
- **Parallel safe:** `false`
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Candidate required:** `true`
- **Commit required:** `true`
- **Supersedes:** `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R5` for future execution
- **Maximum claim:** repaired source Candidate + verifier evidence + independent acceptance only; no runtime activation
- **Source mode:** `APPROVED_NON_SPEC`
- **Source basis SHA-256:** `a9da77c251db97f7946664df9d59271670d94ea3c8dc1ff52dfebd6ffe2886e2`
- **Source comments:** #973 comments `5812072505` and `5814508223`
- **Owner decision:** `#973 改走 GOVERNED，繼續完成。`
- **Owner decision SHA-256:** `5174003b3aaa71e7df82cc2d99395479541763d10f8fb6b9a5322689e4ec64d5`
- **Tracking base:** `de890978e23eff2b0ae871faa24157ccce534340`
- **Prior donor Candidate:** PR #1098 head `cf3547d6056cd0aea1b1641f43cf0569269026af` — evidence/donor only, not acceptable or merge authority

## Goal

Produce one new governed #973 Candidate that:

1. preserves the already-supported fresh pre-DISPATCH authority check;
2. preserves trusted downstream Gateway reconciliation as the terminal truth source;
3. fails closed when any **other** #973 runtime attempt is durably effect-committed but lacks trusted terminal closure;
4. allows a fresh successor only after that prior attempt has trusted terminal closure;
5. preserves same-attempt post-DISPATCH continuity across launch-window expiry or revocation without creating a second effect.

## Observable outcome

A hostile test proves this sequence fails closed before the successor executor is invoked:

```text
attempt A -> durable DISPATCHED -> outcome unresolved
attempt B -> fresh authority / new runtime_attempt_id / new request+fence
          -> BLOCKED before PREPARED/DISPATCHED/executor
          -> blocker identifies attempt A / request / fence
```

A second hostile test proves trusted terminal closure of attempt A unblocks a fresh successor attempt.

## Non-goals

- no rewrite of `scripts/ops/mcp_gateway_durable.py`;
- no new runtime manager, global recovery owner, router, planner, or authority store;
- no generic launchctl/plist/PID/process authority;
- no live runtime activation during verification;
- no reuse of R5 Candidate `3d88a614...` or PR #1098 as an accepted Candidate;
- no approval, integration, merge, release, deployment/public-readiness, or production authority;
- no weakening of expiry, revocation, replay, request/fence, rollback, or tamper guards.

## Source lineage

| Source | Role | Preserved constraint |
|---|---|---|
| Issue #973 body | original product/engineering contract | one-shot typed `RUNTIME_RECOVERY`, no arbitrary command/path/source authority |
| #973 comment `5812072505` | phase refinement | PRE_EFFECT_AUTHORITY and EFFECT_CONTINUITY are distinct; post-effect continuation must reconcile same effect |
| #973 comment `5814508223` | falsification + repair contract | unresolved prior effect must fence a fresh successor attempt |
| PR #1098 `cf3547d...` | donor/evidence only | original two High fixes remain required, but PR is `REVERIFY_REQUIRED` |
| R5 Card | historical adoption contract | old immutable Candidate cannot be reused after material contract delta |

## Allowed repository paths

Worker mutation is limited to the existing #973 implementation surface:

- `nexus/contracts/break_glass_recovery.py`
- `nexus/orchestrator/break_glass_recovery.py`
- `scripts/ops/break_glass_recovery.py`
- `tests/contracts/test_break_glass_recovery_contract.py`
- `tests/nexus/orchestrator/test_break_glass_recovery.py`
- `docs/specs/NEXUS_BREAK_GLASS_RECOVERY_001.md`
- `docs/governance/rollback_runbook.md`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`

### Forbidden scope

- `scripts/ops/mcp_gateway_durable.py`
- `nexus/contracts/gateway_deployment.py`
- `tasks/**`
- any production/runtime state directory
- any secret, credential, host token, launchd state, generated deployment, or durable Gateway ledger

Maximum touched production/source files: 6.  
Maximum touched test files: 2.

## Mandatory source audit before mutation

Re-read current canonical source at the execution base and inspect at minimum:

- all runtime-state readers/writers in `nexus/orchestrator/break_glass_recovery.py`;
- `prepare_runtime_recovery()`, `execute_runtime_recovery()`, and `inspect_runtime_recovery()`;
- current typed runtime attempt directory layout and transition validation;
- existing hostile tamper/replay/lost-ack tests;
- the exact fixed Gateway reconcile/result contract consumed by #973;
- current #973 spec text for expiry, revocation, replay, effect commit, reconciliation, and terminal closure;
- PR #1098 only as donor evidence, never as current source authority.

Do not assume PR #1098 is current or cherry-pickable. Rebind to current main and reconstruct only the allowed behavioral delta.

## Start-state classification

`DEFECT_REPRODUCED` by the bounded static falsification witness in #973 comment `5814508223`.

The first implementation proof must convert that witness into a failing hostile test against the exact new execution base before applying the repair.

## Required invariants / acceptance criteria

### AC-R6-01 — Cross-attempt unresolved-effect fence

When any other #973 attempt has durable `DISPATCHED`/effect-committed state without trusted terminal closure, a fresh attempt with a different `runtime_attempt_id`, request ID, and fence fails closed **before** its executor/effect seam can run.

### AC-R6-02 — Exact blocker binding

The block identifies the prior recovery ID, runtime attempt ID, request ID, and fence strongly enough to direct reconciliation of the exact unresolved attempt. It must not authorize replay or a replacement effect.

### AC-R6-03 — Malformed/tampered prior state fails closed

Malformed, self-rehashed, semantically inconsistent, ambiguous, or unreadable prior runtime state cannot be interpreted as permission to start a successor effect.

### AC-R6-04 — Trusted terminal closure unblocks successor

A prior attempt unblocks a fresh successor only after trusted downstream terminal reconciliation proves closure for that exact prior request/effect.

### AC-R6-05 — Same-attempt continuity preserved

Once the current attempt is durably `DISPATCHED`, expiry or later revocation of the launch authority does not cause a replacement effect. Reconciliation remains bound to the same request/operation/fence and cannot invoke a second physical activation.

### AC-R6-06 — Original High fixes remain closed

The new Candidate must retain:

1. fresh time + current revocation evidence immediately before durable `DISPATCHED`;
2. terminal truth derived from trusted Gateway reconcile/readback rather than outer self-authenticating transition hashes;
3. semantic tamper checks for PREPARED/DISPATCHED/TERMINAL fields and terminal replay denial.

### AC-R6-07 — Specification clarity

`docs/specs/NEXUS_BREAK_GLASS_RECOVERY_001.md` explicitly describes:

- PRE_EFFECT_AUTHORITY;
- EFFECT_CONTINUITY;
- cross-attempt unresolved-effect exclusion;
- trusted terminal closure as the unblock condition;
- no blind successor/retry while an earlier effect remains unresolved.

### AC-R6-08 — No duplicate authority

The repair may add a bounded scan/index/lock **inside the existing #973 consumer state model** only as needed to enforce the invariant. It must not create a second runtime manager, second canonical authority store, or new ownership domain.

## RED / hostile proof

Before GREEN, add a focused failing test with a fake executor proving:

1. attempt A reaches durable effect-committed state;
2. trusted terminal outcome is absent;
3. attempt B uses fresh authority and a distinct attempt/request/fence;
4. attempt B is rejected before executor invocation;
5. executor/effect call count for B remains zero.

Also add a negative-control test that trusted terminal closure for A allows B to proceed through the ordinary pre-effect path.

## Implementation constraints

- minimal behavioral delta;
- prefer reusing existing typed state parsers and trusted Gateway terminal verification;
- fail closed on unknown prior state;
- do not infer terminal closure from transition self-hash alone;
- preserve exact request/fence identity through post-effect reconciliation;
- no filesystem-global lock that becomes a new authority owner;
- no change to CapabilityPlanner, Workforce Admission, merge policy, release policy, or production authority;
- backward compatibility for existing terminal historical attempts unless the contract explicitly rejects malformed/tampered state.

## Mandatory verification

Run from the exact Candidate checkout after dependency bootstrap as required:

1. `uv sync --all-groups --all-extras`
2. `uv run pytest -q tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
3. `uv run pytest -q tests/ops/test_bootstrap_authority_files.py::test_external_bootstrap_recovery_boundary_is_fail_closed`
4. `uv run ruff check nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
5. `uv run ruff format --check --preview nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
6. `uv run python -m py_compile nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py`
7. `git diff --check`

Required result: all commands pass on the exact Candidate. Pre-existing unrelated baseline failures must be identified and separated; they are not repair PASS.

## Physical evidence required

The execution receipt / implementation report must bind:

- exact starting main and task-card blob/hash;
- exact worker/attempt identity;
- exact Candidate head/tree and base;
- complete changed-file list and deletion audit;
- RED witness before repair;
- GREEN hostile cross-attempt tests;
- original two High-regression witnesses;
- verifier command results;
- evidence that `scripts/ops/mcp_gateway_durable.py` and `nexus/contracts/gateway_deployment.py` are unchanged;
- zero live runtime recovery activation during source verification.

## Independent review

A fresh independent reviewer must inspect the exact Candidate after implementation and verify:

1. scope and Task Card compliance;
2. original two High findings remain closed;
3. cross-attempt unresolved-effect exclusion cannot be bypassed by a fresh attempt ID/request/fence;
4. malformed/tampered prior state fails closed;
5. trusted terminal closure is the only unblock seam;
6. same-attempt post-DISPATCH continuity still prevents duplicate physical effects;
7. no duplicate runtime/authority owner was introduced;
8. tests are hostile enough to reject a false-green implementation;
9. no runtime/release/production claim exceeds source evidence.

Implementer PASS is not acceptance.

## Exit conditions

### PASS

A new exact Candidate, based on current canonical main, satisfies AC-R6-01 through AC-R6-08, all mandatory verifiers pass, and an independent acceptance artifact is bound to that exact Candidate.

### BLOCK

Stop on any of:

- current main/card drift before mutation;
- unresolved prior external effect in the **implementation execution** itself;
- required scope widening outside this Card;
- inability to prove trusted terminal closure semantics;
- duplicate authority/manager design pressure;
- verifier or independent-review failure.

### Residual debt

Live activation of the #973 consumer remains unproven and outside this Card even after source acceptance.

### Next gate

After independent acceptance only: Owner Architecture Approval + governed completion for the **new R6 Candidate**. Do not reuse R5 adoption or PR #1098 acceptance evidence.

`AUTO_CHAIN=false`.
