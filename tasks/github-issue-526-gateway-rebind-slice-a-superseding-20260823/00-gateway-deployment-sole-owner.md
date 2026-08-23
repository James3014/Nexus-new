# TASK-526-A — Gateway deployment contract and sole process owner

```yaml
task_id: TASK-526-A
issue: 526
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
claim_mode: MANUAL_DISPATCH
base_main: 2df9a429eb30aca9b20aaa46be9a96ba13c4334a
base_tree: ff8a854ff33fd656044fe80c99d41b1e1984cbd4
work_branch: codex/issue-526-gateway-deployment-contract
supersedes_card_sha256: d4b66f4a96ee52287a5805f5e1fdc438a4f94cab7f98fb9be35a691aaef5bb4d
supersedes_failed_attempt: 44f228e15878b3cae4620db7d7510e4b51cf932c
claim_ceiling: NEXUS_GATEWAY_REBIND_MANAGER_CONTRACT_SOURCE_CANDIDATE_ONLY
```

## Durable source contract

This Card consumes:

- Issue #526 body and G0 contract;
- `ISSUE526_G0_STABLE_SUPERVISOR_SINGLE_OWNER_DESIRED_STATE_DELTA`;
- `ISSUE526_G0_SUPERVISOR_REACHABILITY_SERIALIZE_AFTER_398`;
- `ISSUE526_GATEWAY_REBIND_CONTROL_PLANE_G0_FROZEN`;
- `ISSUE526_SLICE_A_HARD_BLOCK_CARD_REDESIGN_REQUIRED`;
- current Owner approval for this superseding four-file scope.

It authorizes one source/test Candidate only. It does not authorize stable
artifact installation, LaunchAgent adoption/reload/rollback, DevSpace mutation,
TASK-001 dispatch, approval, integration, protected merge, release, or
production claims.

## Objective

Define one deep, pure Gateway deployment contract and make
`mcp_gateway_durable.py` its sole process-effect owner. The implementation
must safely express explicit current/desired deployment profiles, stable
manager artifact identity, Gateway-only preflight/effect/postflight/rollback,
inter-process crash-safe fencing, physical lifecycle quiescence, authenticated
MCP client binding, and desired-versus-loaded reconciliation without creating
a generic process manager or second authority.

## Exact mutation scope

Allowed paths, maximum four:

- `nexus/contracts/gateway_deployment.py` — pure typed contract, canonical
  hashes, state transitions, validation; no filesystem/process/network effects.
- `scripts/ops/mcp_gateway_durable.py` — single Gateway process owner and
  fixed CLI/effect adapter.
- `tests/contracts/test_gateway_deployment_contract.py` — exhaustive pure
  contract/tamper/state-transition tests.
- `tests/ops/test_mcp_gateway_durable.py` — effect/ledger/reconcile/rollback/
  postflight/legacy regression tests.

Create only the two named new files. Delete none. Do not edit UnifiedMCPGateway,
Gateway HTTP/stdio source, DevSpace, route/Planner/Workforce policy, Task Cards
during implementation, runtime state, generated files, or unrelated paths.

## Authority and workforce

- execution role: `main_engineering`
- intended worker candidate: `codex_luna / codex / gpt-5.6-luna`
- fresh exact Workforce Admission: required after final Card hash
- governed adapter and worker receipt: required
- independent verifier: required and distinct from implementer
- `AUTO_CHAIN=false`

The worker may commit one scoped Candidate but may not push, merge, approve,
integrate, install, reload, clean unrelated state, or select successor work.

## Architecture invariants

1. `GatewayDeploymentRequest`, profiles, receipts, and state transitions are
   deterministic and side-effect free in the contract module.
2. `mcp_gateway_durable.py` remains the only owner of plist/filesystem/
   launchctl/loopback effects. The contract module never executes.
3. DevSpace is transport/auth only in future Slice B and is never a process
   owner. Slice A performs zero DevSpace validation or effects.
4. A deployed stable manager artifact is the same accepted manager authority,
   hash-bound under the existing external Nexus state boundary, not a second
   implementation or source of truth.
5. Explicit desired deployment identity is not inferred from GitHub main.

## Required behavior — pure contract

1. Use strict, extra-forbid typed schemas for:
   - repository and trusted deployment profile;
   - current and desired root/Git-toplevel/remote/HEAD/tree;
   - fixed interpreter path/hash and Gateway entrypoint;
   - authority receipt identity/scope/freshness/request binding;
   - current plist/service/PID/server/source/tool/schema/permission identity;
   - durable lifecycle/assist quiescence evidence;
   - rollback plist, stable artifact, source, loaded-state, and client identity;
   - postflight required/observed identities;
   - request ID, canonical request hash, idempotency fence, effect class;
   - versioned ledger states and typed result/blocker classes.
2. Bind both immediate profiles explicitly:
   - current/rollback: `Nexus-new-482a79fe@67521fe9...`;
   - desired: `Nexus-new-935a9dd3@7ad264e1.../b9057f8e...`.
   These are canary evidence, not a permanent auto-follow-main rule.
3. Do not bind a DevSpace build/package hash into Nexus Gateway source trust.
4. State machine:
   `REQUESTED -> PREFLIGHTED -> STARTED -> SERVICE_OBSERVED ->
   IDENTITY_VERIFIED -> CLIENT_BOUND -> VERIFIED`, with
   `UNCERTAIN_EFFECT`, `ROLLBACK_STARTED`, `ROLLED_BACK`, and
   `BLOCKED` fail-closed branches.
5. Unknown fields, malformed hashes, stale evidence, operation substitution,
   authority/profile/scope mismatch, missing predecessor, invalid transition,
   or replay conflict fail before effects.

## Required behavior — sole manager

1. Stable artifact installation is a separate exact operation. It sources bytes
   only from an accepted clean source root bound to exact HEAD/tree/path/blob
   hash and records source/card/authority/request identities, artifact SHA-256,
   numeric UID/mode, predecessor artifact, install fence, and rollback receipt.
   Normal Gateway reload never silently replaces the manager artifact.
2. Trusted deployment profile validation uses resolved absolute roots, exact Git
   toplevel and remote repository, exact HEAD/tree, clean/trust rule, fixed
   entrypoint, and fixed interpreter path/hash. A caller boolean is not trust.
3. Gateway-only actions use a fixed service label/plist/log/profile. Caller
   input cannot select a command, executable, label, PID, plist path,
   environment override, root outside an admitted profile, or another service.
4. Preflight freshly captures the physical current plist hash/bytes, loaded
   state, launchd service/PID, listener/endpoint, Gateway server/root/HEAD,
   stable artifact identity, lifecycle/assist actionable state, and exact
   rollback predecessor. It compares these to the typed request.
5. Current `pending_actions` is durable state, never an action to complete.
   A running/uncertain mutation requires drain/hold/reconcile. Failed historical
   attention state may proceed only with exact durable reacquisition evidence.
6. Before the first process/file effect, acquire an inter-process lock and
   atomically persist `STARTED` with canonical request hash and pre-effect
   identities. An unreadable/malformed/version-mismatched ledger fails closed.
7. Duplicate/replayed `STARTED` physically reconciles the serving
   plist/process/server/source before deciding; it never bootstraps a second
   Gateway blindly.
8. Launch/reload/adopt changes only
   `com.nexus.mcp.gateway.direct`. It preserves atomic writes/fsync/rename,
   strict absent-service classification, unrelated launchctl failure rejection,
   evidence before effect, and zero DevSpace effects.
9. Production postflight uses bounded loopback retries and the persisted secret
   token to perform:
   - `/health` identity read;
   - authenticated MCP `initialize`;
   - authenticated `tools/list`;
   - tool-manifest and full-schema recomputation.
   It verifies new server instance, desired root/HEAD/tree, runtime/action/tool/
   permission/task/lifecycle identities, required actions, and authenticated
   client binding before `VERIFIED`.
10. Missing acknowledgement, timeout, malformed response, old instance, wrong
    identity, or partial start becomes `UNCERTAIN_EFFECT` and reconciles
    physically before retry.
11. Rollback is independent of the failed desired target. It strictly parses
    and verifies the captured fixed Gateway plist/artifact/source/loaded-state,
    restores only that coherent predecessor under the same lock, bootstraps only
    when previously loaded, and verifies old service/source/client identity.
12. Stable receipt, ledger, request, and rollback stores enforce safe directory
    chain, restrictive modes, numeric owner, no symlinks, bounded size, atomic
    CAS/write, and tamper fail-closure.
13. Legacy dual-service APIs remain explicit compatibility only and cannot back
    the new Gateway-only operation.
14. No result grants Task Card, Planner, Workforce, Candidate, approval,
    integration, merge, release, or production authority.

## Acceptance and negative controls

- AC-1: pure schemas/hashes/transitions are deterministic and reject unknown,
  malformed, stale, substituted, or invalid-state input.
- AC-2: the old internally consistent Gateway fails desired-profile comparison
  against the explicit newer target even when its internal reload flag is false.
- AC-3: wrong/outside/symlink root, wrong repo/toplevel/HEAD/tree, dirty target,
  missing entrypoint, wrong interpreter/hash, and caller self-trust all fail
  before effect.
- AC-4: operation substitution, stale authority, wrong action/profile/scope,
  arbitrary command/executable/label/PID/plist/env/service, and multi-service
  requests are unrepresentable or rejected.
- AC-5: stable artifact source/commit/tree/blob/hash/UID/mode/predecessor/
  request substitution fails; normal reload never installs it.
- AC-6: every Gateway-only operation performs zero DevSpace reads requiring
  validation, writes, bootout, bootstrap, reload, or uninstall.
- AC-7: ambiguous legacy/`.direct` ownership, wrong port/listener, stale
  current identity, and invalid adoption evidence fail closed.
- AC-8: running/uncertain lifecycle or assisted action blocks; exact durable
  failed-attention reacquisition remains representable without fake success.
- AC-9: malformed ledger, lock contention, concurrent request, duplicate fence,
  and crash after STARTED reconcile without a second launch.
- AC-10: wrong/missing health, initialize, tools/list, manifest/full schema,
  permission/action/task/lifecycle identity, required action, server/root/HEAD/
  tree, or client binding never becomes VERIFIED.
- AC-11: bootstrap/postflight failure restores exact predecessor loaded/unloaded
  state or returns evidence-preserving UNCERTAIN/BLOCKED; no ordinary failure
  leaves false rollback success.
- AC-12: rollback rejects altered plist label/program args/interpreter/root/log/
  env/artifact/source/digest and never affects DevSpace/unrelated state.
- AC-13: existing secret parsing, ancestry floor, absent-service classifier,
  atomic legacy rollback, and exec-boundary tests remain green.

## Verification commands

```bash
uv run pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
uv run ruff check nexus/contracts/gateway_deployment.py scripts/ops/mcp_gateway_durable.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
git diff --check
git diff --cached --check
git diff --cached --name-status
git diff --name-status 2df9a429eb30aca9b20aaa46be9a96ba13c4334a...HEAD
```

Before commit inspect full staged diff, staged/tracked deletions, both stats, and
exact four-path scope. Record versions, command exits/test counts, Candidate
commit/tree, and file fingerprints.

## Independent review

The reviewer must bind exact base/head/tree/Card hash, rerun every verifier,
inspect all four files, challenge false-green tests and shallow mocks, and prove
that no source/test result is presented as installation/reload/runtime evidence.

## Dependencies and claim ceiling

- Slice A source/test work is disjoint from PR #521 and #398.
- Slice B DevSpace action remains separate and
  `SERIALIZE_AFTER:#398` for live action/canary.
- Final `NEXUS_CANONICAL_LOCAL` canary is a separate authority/evidence gate.

Maximum claim:
`NEXUS_GATEWAY_REBIND_MANAGER_CONTRACT_SOURCE_CANDIDATE_ONLY`.

## Exit conditions

- `PASS`: one exact four-path source/test Candidate satisfies every AC and
  verifier.
- `REVISE`: bounded correction stays within four paths.
- `RECOVERABLE_BLOCK`: transient environment failure with reconciled
  workspace/process state.
- `HARD_BLOCK`: authority conflict, security weakening, scope widening,
  duplicate process owner, unexpected deletion, unresolved semantics, or
  required verifier failure.
