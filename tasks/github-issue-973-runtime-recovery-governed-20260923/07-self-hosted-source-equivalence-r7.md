# ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R7 — Self-hosted source-equivalence execution repair

This Card is the bounded governed successor to R6 for Issue #973. It preserves every R6
behavioral obligation and repairs one self-hosting execution-base contradiction proven after
the terminal A14 Gateway recovery.

It does **not** authorize live use of the #973 Runtime Recovery consumer, Gateway recovery,
release, production claims, or reuse of any earlier Candidate as accepted evidence.

- **Campaign:** `github-issue-973-runtime-recovery-governed-20260923`
- **Task ID:** `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R7`
- **Attempt ID:** new attempt identity required at execution time
- **Status:** `ACTIVE_AFTER_TRACKING_AND_GATEWAY_VISIBILITY`
- **Issue:** `973`
- **Execution lane:** `GOVERNED`
- **Auto-chain:** `false`
- **Parallel safe:** `false`
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Candidate required:** `true`
- **Commit required:** `true`
- **Supersedes:** `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R6` for future execution
- **Maximum claim:** repaired source Candidate + verifier evidence + independent acceptance only; no runtime activation
- **Source mode:** `APPROVED_NON_SPEC`
- **Source comments:** #973 comments `5812072505`, `5814508223`, and `5817558406`
- **Owner decision:** `#973 改走 GOVERNED，繼續完成。`
- **Owner completion instruction:** `你處理完後合併`

## Why R7 exists

R6 required the implementation attempt to start from raw current GitHub `main` and to block
on any main drift. That cannot converge with the accepted tracked #526 recovery-carrier
architecture:

1. the recovery authority receipt must first be tracked on canonical `main`;
2. the receipt binds a desired functional Gateway source selected before the receipt merge;
3. merging the receipt advances `main`;
4. therefore the loaded functional source is necessarily an ancestor of the receipt-bearing
   current main even when no executable #973 byte changed.

A14 proved this mechanically:

- terminal A14 operation: `op_ab6fca640908721d`;
- A14 result: `VERIFIED`;
- loaded source: `c8da43aaab92dbd5d11734aeb15d6ee5dc23931d / c174e09b7b77eb5edb5de6883434fca180f28175`;
- current main after A14 carrier: `f21791a5f03d8b4cdc32c26a057c4bfbecc36051 / b706450ac7a193c8fa17609f0ae8ace8bcf98b3c`;
- execution-readiness result for raw current-main identity:
  `BLOCKED / SOURCE_REALM_MISMATCH / BIND_EXACT_DESIRED_SOURCE_IDENTITY`;
- diff from loaded source to that current main touched only:
  `scripts/ops/trusted_deletion_anchor.py`,
  `tests/ops/test_trusted_deletion_anchor.py`, and the rolling #526 recovery receipt;
- no R6 Card, #973 implementation, #973 test, or #973 specification byte changed.

R7 fixes the freshness predicate; it does not reduce verification.

## Goal

Produce one new governed #973 Candidate that:

1. preserves fresh pre-DISPATCH authority/revocation checking;
2. preserves trusted downstream Gateway reconciliation as terminal truth;
3. blocks a fresh successor while another #973 attempt is durably effect-committed without
   trusted terminal closure;
4. allows a successor only after trusted terminal closure of that exact prior effect;
5. preserves same-attempt post-DISPATCH continuity across launch-window expiry/revocation;
6. executes from a proven material-equivalent functional base when raw-main equality is
   impossible solely because of self-hosting authority/evidence carriers;
7. is rebound/rebased to then-current GitHub main and fully reverified before acceptance.

## Material-equivalent execution-base rule

A governed R7 worker may start from a functional source commit that is a strict ancestor of
fresh GitHub main **only** when all of the following are proven immediately before mutation:

1. fresh GitHub main commit/tree are observed;
2. the functional base is an ancestor of that main;
3. the exact R7 Card bytes and campaign INDEX bytes are present and identical in both;
4. every path in the R7 protected set below is byte-identical between the functional base and
   fresh main;
5. any changed path outside that protected set is classified as authority/evidence-carrier or
   unrelated work and cannot alter #973 execution semantics;
6. there is no ambiguous or unresolved prior implementation-worker effect;
7. the material-equivalence witness records base/main identities and the exact changed-path
   set before mutation.

Any protected-path change, Card/INDEX change, deletion, unreadable path, ancestry failure,
or uncertain comparison is `BLOCK`.

This rule applies only to this self-hosting source seam. It is not general permission to run
governed work from stale source.

## Protected set for the pre-mutation equivalence gate

The exact R7 Card and INDEX plus:

- `nexus/contracts/break_glass_recovery.py`
- `nexus/orchestrator/break_glass_recovery.py`
- `scripts/ops/break_glass_recovery.py`
- `tests/contracts/test_break_glass_recovery_contract.py`
- `tests/nexus/orchestrator/test_break_glass_recovery.py`
- `docs/specs/NEXUS_BREAK_GLASS_RECOVERY_001.md`
- `docs/governance/rollback_runbook.md`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`
- root `AGENTS.md`
- `docs/governance/current_operating_mode.yaml`

## Allowed repository paths

Worker mutation remains limited to the existing #973 implementation surface:

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

Maximum touched production/source/docs files: 6.  
Maximum touched test files: 2.

## Behavioral acceptance criteria

R7 inherits AC-R6-01 through AC-R6-08 unchanged:

### AC-R7-01 — Cross-attempt unresolved-effect fence

When any other #973 attempt has durable `DISPATCHED`/effect-committed state without trusted
terminal closure, a fresh attempt with a different runtime attempt ID, request ID, and fence
fails closed before its executor/effect seam can run.

### AC-R7-02 — Exact blocker binding

The block identifies the prior recovery ID, runtime attempt ID, request ID, and fence strongly
enough to direct reconciliation of that exact unresolved attempt. It grants no replay or
replacement effect.

### AC-R7-03 — Malformed/tampered prior state fails closed

Malformed, self-rehashed, semantically inconsistent, ambiguous, or unreadable prior runtime
state cannot be interpreted as permission to start a successor effect.

### AC-R7-04 — Trusted terminal closure unblocks successor

A prior attempt unblocks a fresh successor only after trusted downstream terminal
reconciliation proves closure for that exact prior request/effect.

### AC-R7-05 — Same-attempt continuity preserved

Once the current attempt is durably `DISPATCHED`, expiry or later revocation does not cause a
replacement effect. Reconciliation remains bound to the same request/operation/fence.

### AC-R7-06 — Original High fixes remain closed

Retain:
1. fresh time + current revocation evidence immediately before durable `DISPATCHED`;
2. terminal truth from trusted Gateway reconcile/readback rather than outer transition hashes;
3. semantic tamper checks for PREPARED/DISPATCHED/TERMINAL and terminal replay denial.

### AC-R7-07 — Specification clarity

The break-glass spec explicitly covers PRE_EFFECT_AUTHORITY, EFFECT_CONTINUITY,
cross-attempt unresolved-effect exclusion, trusted terminal closure, and no blind successor.

### AC-R7-08 — No duplicate authority

No second runtime manager, canonical authority store, router, planner, or ownership domain.

### AC-R7-09 — Material-equivalence is narrow and falsifiable

The pre-mutation witness must fail on any protected-path or Card/INDEX drift. A negative test
or deterministic comparison must prove that protected drift is not silently accepted.

### AC-R7-10 — Final current-main rebind

The implementation worker may produce its first Candidate from the proven functional base,
but that Candidate is not acceptable or mergeable until its exact diff is reapplied/rebased
onto then-current GitHub main, all mandatory verifiers pass there, and independent acceptance
binds that exact final Candidate.

## Mandatory RED / hostile proof

Before GREEN, convert the R6 falsification into a failing hostile test:

1. attempt A reaches durable effect-committed state;
2. trusted terminal outcome is absent;
3. attempt B uses fresh authority and distinct attempt/request/fence;
4. B is rejected before executor invocation;
5. executor/effect call count for B is zero.

Also prove trusted terminal closure for A unblocks B.

## Execution constraints

- Re-read current canonical source at the selected functional base.
- Do not cherry-pick PR #1098.
- Use PR #1098 only as donor/evidence.
- Minimal behavioral delta.
- Prefer existing typed state parsers and trusted Gateway terminal validation.
- Fail closed on unknown prior state.
- Do not infer terminal closure from self-hash.
- No filesystem-global lock that becomes a new authority owner.
- No live Runtime Recovery activation during source verification.
- `AUTO_CHAIN=false`.

## Dispatch verifier ceiling vs complete verification

The current canonical `nexus_worker_candidate` ingress accepts at most four bounded verifier
commands and rejects shell composition tokens. That ingress limit does not reduce this Card's
verification obligation.

The worker dispatch may carry these four bounded commands:

1. `uv run pytest -q tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py tests/ops/test_bootstrap_authority_files.py::test_external_bootstrap_recovery_boundary_is_fail_closed`
2. `uv run ruff check nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
3. `uv run ruff format --check --preview nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
4. `uv run python -m py_compile nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py`

Before acceptance, the coordinator must still run the complete R6 verifier set exactly,
including dependency sync and `git diff --check`.

## Complete mandatory verification on the final current-main Candidate

1. `uv sync --all-groups --all-extras`
2. `uv run pytest -q tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
3. `uv run pytest -q tests/ops/test_bootstrap_authority_files.py::test_external_bootstrap_recovery_boundary_is_fail_closed`
4. `uv run ruff check nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
5. `uv run ruff format --check --preview nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
6. `uv run python -m py_compile nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py`
7. `git diff --check`

## Independent acceptance

A fresh reviewer must bind the exact final current-main Candidate and verify:

- scope and Card compliance;
- the material-equivalence witness was valid for the worker start;
- final Candidate is actually based on then-current main;
- AC-R7-01..10;
- original two High findings remain closed;
- hostile tests are false-green resistant;
- no duplicate authority/manager;
- no runtime/release/production claim exceeds evidence.

Implementer PASS is never acceptance.

## Exit

### PASS

A new final Candidate based on then-current GitHub main satisfies AC-R7-01..10, the complete
verifier suite passes, and independent acceptance is bound to that exact Candidate.

### BLOCK

Stop on protected-path/Card drift, ambiguous comparison, unresolved implementation-worker
effect, required scope widening, inability to prove terminal semantics, verifier failure, or
independent-review failure.

### Residual debt

Live activation/canary of the new #973 Runtime Recovery consumer remains a separate post-source
gate even after implementation merge.

### Next gate

After independent acceptance only: Owner Architecture Approval + governed completion for the
new exact R7 Candidate, then post-merge source readback. Runtime canary remains separately
authorized.

`AUTO_CHAIN=false`.
