# TASK-526-B-AUTHORITY — Separate source provenance from host-effect authority

```yaml
task_id: TASK-526-B-AUTHORITY
issue: 526
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
claim_mode: MANUAL_DISPATCH
base_main: ac4a9ab1e0180170ca062cdc81f2142bca8bd80f
base_tree: db329f4931b55b74f1e1f9fe61f7edf4ca8422bc
work_branch: codex/issue-526-host-rebind-canary
host_card_sha256: fcd22da4ef92b7cde004523fe900c06bc1b9e67715049c95383c581e640f631f
claim_ceiling: NEXUS_GATEWAY_HOST_AUTHORITY_CONTRACT_SOURCE_CANDIDATE_ONLY
```

## Problem and authority

Merged Slice A accepts only
`NEXUS_GATEWAY_REBIND_MANAGER_CONTRACT_SOURCE_CANDIDATE_ONLY` in its request
validator, yet the same request can reach install, reload, and rollback. The
merged Slice A Card explicitly grants no host-effect authority. Executing it
would therefore convert source provenance into LaunchAgent authority.

This is a Goal-preserving fail-closed correction authorized by the current
Owner continuation and Issue #526. It authorizes one source/test Candidate
only. It does not authorize stable artifact installation, plist/store writes,
launchctl, Gateway reload/rollback, DevSpace, approval, merge, release, or a
runtime/public claim.

## Exact mutation scope

Modify only these four existing files; create/delete none:

- `nexus/contracts/gateway_deployment.py`
- `scripts/ops/mcp_gateway_durable.py`
- `tests/contracts/test_gateway_deployment_contract.py`
- `tests/ops/test_mcp_gateway_durable.py`

Do not edit Cards during implementation, Gateway HTTP/stdio source, DevSpace,
Planner/route/Workforce policy, runtime state, generated files, or unrelated
paths.

## Required pure contract

1. Preserve a strict source-provenance receipt with exact scope
   `NEXUS_GATEWAY_REBIND_MANAGER_CONTRACT_SOURCE_CANDIDATE_ONLY`. It can prove
   accepted source identity only and can never authorize a physical effect.
2. Add a distinct strict `HostEffectAuthorityReceipt` with exact scope
   `NEXUS_GATEWAY_REBIND_HOST_EFFECT_ONLY` and fields binding:
   - `schema=nexus.gateway.host_effect_authority.v1`, numeric receipt version,
     receipt ID, and canonical receipt hash;
   - `issuer_id=owner-james`, `coordinator_id=coordinator-codex`, and
     `authorized_actor_id=coordinator-codex`;
   - Owner activation ID/hash/source thread frozen by the host Card;
   - standing-grant ID
     `OWNER_STANDING_COORDINATOR_20260818_DURABLE_GITHUB_WORKFLOW` and receipt
     SHA-256
     `3b8895f093692257d6225fbb8150b34f520e667d250c7817ad120cefd42751d5`;
   - source-provenance base merge/tree
     `ac4a9ab1e0180170ca062cdc81f2142bca8bd80f` /
     `db329f4931b55b74f1e1f9fe61f7edf4ca8422bc`;
   - exact post-correction merge SHA/tree, independent acceptance receipt hash,
     final manager SHA-256, and current main SHA, supplied only after this Task
     is accepted and merged;
   - host Card path/ID/SHA-256
     `TASK-526-HOST-1` /
     `fcd22da4ef92b7cde004523fe900c06bc1b9e67715049c95383c581e640f631f`;
   - exact operation and `EffectClass`;
   - fixed service label, plist, endpoint, desired/current profile hash;
   - request ID and idempotency fence;
   - exact `receipt_version=1`; unknown versions fail closed;
   - issued/expires timestamps, `revocation_state=NOT_REVOKED`,
     `revoked_at=null`, and `revocation_reason=null`.
3. A deployment request carries source provenance plus an optional typed host
   receipt. Every Gateway status/preflight/install/reload/rollback request requires
   both; source-only host requests fail before observation or effect. There is
   no automatic legacy upgrade or scope-string coercion.
4. Host receipt operation/effect/request/fence/profile/service/Card/source or
   freshness mismatch fails closed. Unknown fields and cross-operation reuse
   fail. Revocation must be exactly active/not-revoked.
5. `status` is a separate `STATUS` host operation that reads only the fixed
   Gateway service; legacy dual-service `manage("status")` is not a host
   authority surface. Every distinct operation pair across status, preflight,
   install, reload, and rollback must reject cross-use before observation.
6. Canonical request hashing covers both receipts. Each receipt has its own
   canonical hash; a source receipt hash cannot substitute for host authority.

## Required manager enforcement

1. Add a fixed owner-only canonical host-authority store:
   `/Users/jameschen/Library/Application Support/Nexus/gateway-direct/host-authority.json`.
   It requires numeric UID `501`, file mode `0600`, maximum size 64 KiB,
   directory UID `501`/mode `0700`, no symlink, safe ancestry, duplicate-key
   rejection, and the exact strict top-level schema above. Caller input cannot
   select another path. Request/evidence/ledger/lock stores also require UID
   `501`/mode `0600`; installed manager mode is `0700`.
   The non-self-issued source is the fixed Git-tracked path
   `tasks/github-issue-526-host-authority-and-canary-20260823/02-host-effect-authority-receipt.json`
   on public remote `https://github.com/James3014/Nexus-new.git` `main`. Before
   effects the manager must use fixed Git commands to read remote main, require
   a clean trusted source HEAD equal to remote main, read that exact blob with
   `git show`, and require byte equality with the local canonical store. No
   caller may select the remote/ref/path or substitute a local commit/branch.
2. Before any physical observation for a host request and before every first
   artifact/plist/process/network effect, load the canonical host receipt and
   require exact equality with the request receipt plus the pure contract.
3. CLI continues to accept only fixed request/evidence stores and fixed action
   choices. It never accepts a host receipt path, issuer, command, executable,
   label, plist, PID, environment, service, source root, or profile from argv.
4. `install_stable_artifact`, `gateway_reload`, and `rollback_gateway` reject
   source-only authority before source reads, destination writes, token loads,
   HTTP, ledger writes, plist writes, or launchctl calls.
5. Ledger records bind the host receipt hash, accepted source merge/tree, host
   Card SHA, effect class, operation, and idempotency fence. Duplicate fence
   reuse across another request is a conflict. Malformed legacy or new ledger
   data fails closed; no production ledger exists at dispatch preparation.
6. Legacy dual-service APIs remain explicit compatibility only and cannot
   provide Gateway host authority.
7. Only coordinator `coordinator-codex`, acting from the frozen Owner
   activation in the host Card after this Task's exact merge/acceptance, may
   issue the canonical host receipt. Owner `owner-james` is the sole revocation
   authority through atomic replacement of the same fixed store. The source
   worker cannot issue, activate, or revoke a receipt.
8. `_safe_store_path` and every direct canonical store/lock seam enforce the
   exact Card modes, not merely absence of group/other write bits.

## Acceptance and negative controls

- source-only status/preflight/install/reload/rollback: reject with zero observer,
  token, HTTP, filesystem, ledger, plist, runner, or launchctl calls;
- missing/unknown/self-issued/unstored host receipt: reject;
- same-UID locally fabricated receipt, unmerged branch receipt, wrong remote
  main, dirty/source-divergent receipt, or local/Git-tracked byte mismatch:
  reject before observation/effect;
- wrong repository/Owner/coordinator/standing grant/source merge/tree/Card
  ID/hash/service/plist/endpoint/profile/request/fence/operation/effect: reject;
- stale, future-issued, revoked, malformed, hash-invalid receipt: reject;
- every cross-operation receipt reuse pair across status, preflight, install,
  reload, and rollback: reject before observer/token/runner calls;
- same fence on a different request: reject; duplicate STARTED/uncertain request
  physically reconciles and never launches twice;
- `StableArtifactIdentity.authority_receipt_id` must equal the accepted host
  receipt ID;
- current positive install/reload/rollback tests must use a valid separate host
  receipt and canonical-store fixture, not the source receipt helper;
- legacy source-only false-green helpers are retained only for explicit
  rejection tests.
- execute stale, future, revoked, actor/issuer/coordinator/grant, missing store,
  symlink, wrong UID/mode, oversized, duplicate-key, all distinct
  cross-operation pairs, same-fence/different-request, ledger-field binding,
  and positive fixed-Gateway STATUS tests. Do not mock above the seam.

## Verification

```bash
uv run pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
uv run ruff check nexus/contracts/gateway_deployment.py scripts/ops/mcp_gateway_durable.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
uv run ruff format --check --preview nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
python3 -m py_compile nexus/contracts/gateway_deployment.py scripts/ops/mcp_gateway_durable.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
git diff --check
```

Independent review must bind exact base/head/tree/Card hashes, inspect the full
four-file diff, challenge self-issued/caller-supplied authority and false-green
test seams, and preserve the source-only claim ceiling.

## Dependencies and exit

- `TASK-526-HOST-1` remains BLOCKED until this Candidate is independently
  accepted and merged. Unlock requires exact merged main SHA/tree, exact
  independent acceptance receipt hash, final manager SHA-256, current-main
  ancestry, separately reviewed/CAS-merged receipt-issuance PR/main SHA/tree,
  and a current valid local receipt byte-identical to the fixed Git-tracked
  remote-main receipt; branch/Card status alone never unlocks it.
- Gateway-only local host canary is not serialized behind #398 because it
  performs zero DevSpace effects. The future DevSpace/ChatGPT-facing action
  canary remains `SERIALIZE_AFTER:#398`.
- `PASS` means only
  `NEXUS_GATEWAY_HOST_AUTHORITY_CONTRACT_SOURCE_CANDIDATE_ONLY`.
- `AUTO_CHAIN=false`; worker stops after one exact source/test Candidate.
