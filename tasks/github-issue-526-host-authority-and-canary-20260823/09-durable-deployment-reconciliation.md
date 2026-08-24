# TASK-526-R1-DURABLE-DEPLOYMENT-RECONCILIATION

```yaml
task_id: TASK-526-R1-DURABLE-DEPLOYMENT-RECONCILIATION
issue: 526
repository: James3014/Nexus-new
source_base: 1e5e89a847eee609d8939c531e29a57838103427
status: ACTIVE
dependencies:
  - PR #554 merge `1e5e89a847eee609d8939c531e29a57838103427`
  - PR #545 merge `16acce53704969fc9093c1c7d90d7fcfa46e51e6c`
dependencies_status: SATISFIED
host_effect_authority: NOT_GRANTED
source_tree: 0d4e1146be68840d34adf907b3028cbf437d9729
r0_xa1_acceptance_sha256: bb419914899d4aa8fffdbb3f8df08b7629560e5c1e2cc9f5878db461b9d4eac0
execution_realm: SOURCE_ONLY
auto_chain: false
claim_mode: MANUAL_DISPATCH
claim_ceiling: NEXUS_GATEWAY_R1_SOURCE_CANDIDATE_ONLY
allowed_file_count: 4
allowed_files:
  - nexus/contracts/gateway_deployment.py
  - scripts/ops/mcp_gateway_durable.py
  - tests/contracts/test_gateway_deployment_contract.py
  - tests/ops/test_mcp_gateway_durable.py
```

## R1-B amendment: verified Git store and complete detached deployments

This amendment supersedes single-file/content-bundle staging while preserving
the stable task ID, source-only realm, `AUTO_CHAIN=false`, and four
implementation/test paths. Candidate `3a97e2f493152e48b66eb2efe18125cbeb1d6f26`
is `REVISE` evidence. Card hash
`e403989a59de80477bb23875f1343da77300d23ddf28da4cd3281e76425ad0e7` is
superseded; the INDEX binds the amended hash after applying exact bytes. The
Card does not self-embed its own content hash.

The staging unit is a complete detached Git worktree for each target and
predecessor. A verified Git bundle containing exact remote-main, desired, and
predecessor refs is imported into one persistent manager-owned bare repository
with no alternates:

    fixed authority mirror -> verified Git bundle ->
    /Users/jameschen/Library/Application Support/Nexus/gateway-direct/repository.git ->
    deployments/<deployment-id> (two full detached checkouts)

The fixed authority mirror is
`/Users/jameschen/Workspace/Nexus-new-authority-main`; origin, clean state,
numeric owner/mode, and `HEAD == fresh remote-main` are verified before bundle
creation. Recovery performs no network fetch and never follows main; the fixed
authority preflight may use `git ls-remote` only to prove the mirror HEAD equals
current remote main. The
canonical dirty checkout and R1 branch are never recovery byte sources.

Deployments are atomically materialized under
`/Users/jameschen/Library/Application Support/Nexus/gateway-direct/deployments/<deployment-id>`.
Each is a Git-aware detached worktree whose gitdir/object store resolves only
through the fixed manager-owned `repository.git`; it has no external alternates,
authority-mirror, or disposable-source dependency. Source bundles
use the fixed path
`/Users/jameschen/Library/Application Support/Nexus/gateway-direct/source-bundles/<recovery-receipt-hash>.bundle`.
The manager derives deployment identity from a canonical semantic recovery
source set: repository, accepted/desired/predecessor commits and trees, fixed
entrypoint paths/blobs/hashes/tracked modes, and interpreter identity. Callers
cannot provide IDs, refs, roots, or paths. Raw Git bundle SHA-256 is physical
transport evidence and never an input to source-set, deployment-ID, manifest,
or receipt authority identity.

### R1-B semantic identity clarification

This clarification breaks the otherwise circular issuance dependency in which
the tracked receipt changes fresh main, fresh main changes the raw bundle, and
the raw bundle hash changes receipt-bound deployment identity. It preserves the
single recovery authority and all exact Git verification requirements.

`RecoverySourceSet` is a strict pure record containing repository;
accepted-source commit/tree; desired and predecessor commit/tree; each role's
fixed entrypoint path, blob OID, SHA-256, and tracked mode; and fixed interpreter
path/resolved path/SHA-256/owner/mode. Its `source_set_sha256` is the canonical
hash of those semantic fields only. It excludes receipt bytes/hash, receipt
merge or observed fresh-main identity, raw bundle hash, timestamps, host paths,
caller refs, and deployment paths.

Each manager-derived `DeploymentManifest` binds its role, repository,
`source_set_sha256`, commit/tree, entrypoint Git identity, interpreter identity,
and a canonical manager-derived deployment ID and manifest hash. Raw bundle
SHA-256 is excluded. The sole `RecoveryAuthorityReceipt` binds the semantic
source set and both expected manager-derived deployment/manifests plus the
accepted R1 source, final manager, independent acceptance, fixed service,
request/fence, authority lineage, validity, and revocation. Its ancestry field
is an authority floor or issuance parent that precedes the receipt merge; it is
not a self-containing future-main claim.

After local receipt bytes equal the tracked blob on fresh remote main, the
manager builds and verifies the exact three-role Git bundle, computes its raw
SHA-256, imports it into the strict fixed bare repository, and verifies the
imported bare-store identity. The manager then constructs and records a strict
`SourceBundleEvidence` row in the same ledger-v2 hash chain before any worktree
promotion. That evidence binds request/hash/fence,
receipt ID/hash, source-set hash, observed fresh-main commit/tree, exact
role-to-commit head map, raw bundle hash/size, bundle verification, bare-store
identity evidence, observation time, and evidence hash. It is not authority and
cannot authorize staging or effect.

Issuance is acyclic: accepted/desired/predecessor Git identity -> semantic
source set and manifests -> receipt -> receipt-bearing fresh main -> raw bundle
and physical evidence -> durable store/worktrees. If fresh main later advances
without changing tracked receipt bytes, semantic deployment identity remains
stable. Once a ledger row records a raw bundle hash for the request, replay must
reverify that exact artifact/head map and may not silently regenerate it.

The fixed tracked receipt is
`tasks/github-issue-526-host-authority-and-canary-20260823/10-durable-recovery-authority-receipt.json`;
the only local receipt is
`/Users/jameschen/Library/Application Support/Nexus/gateway-direct/recovery-authority.json`.
A new strict `GatewayRecoveryRequest` contains only receipt ID/hash reference,
request ID, fence, desired/predecessor manifest references, and fixed recovery
operation data. It excludes legacy authority/current-profile/rollback and all
caller root, command, PID, plist, port, environment, or follow-main fields;
the caller never supplies the receipt body.

The manager validates local receipt bytes, strict schema, R1 Card/source/
manager/acceptance/source-set/manifest bindings, and `git show <fresh-remote-main>:<fixed-receipt-path>` bytes from the verified
authority mirror against the fixed tracked receipt. A caller-rehashed receipt is not authority;
the legacy host-effect bundle is never parsed for recovery.

Ledger v2 recovery rows share the v1 parent-hash chain. They include the
post-receipt `SourceBundleEvidence` physical record; raw bundle SHA-256 is
ledger-bound evidence, not a deployment or receipt identity input. Under the lock, exact
request-hash CAS and unique fence, persist
`REQUESTED -> PREFLIGHTED -> TARGET_READY -> ROLLBACK_READY -> EFFECT_STARTED`
with both full checkouts and pre-effect evidence. Lost acknowledgement becomes
`UNCERTAIN_EFFECT`; reconcile the fixed service/PID-start/listener/plist and
authenticated health, initialize, and tools/list for the same request/fence.
Desired complete postflight yields `VERIFIED`, predecessor yields `ROLLED_BACK`,
and an unprovable state remains `UNCERTAIN_EFFECT`/`BLOCKED`; never launch a
second Gateway. Same request/hash/fence is idempotent; conflicts fail closed.

Schemas, manager logic, and tests remain within the same four allowed files.
Host receipt issuance, mirror refresh, real bundle/bare-repo/worktree
materialization, plist/launchd effect, rollback, and canary are deferred to a
separately authorized host phase.

The required negative canary hides/removes the disposable authority mirror and
original DevSpace roots after both checkouts are staged, then proves
`repository.git` and both deployments still pass Git root/origin/HEAD/tree/
clean/entrypoint tracked-mode/blob/hash checks and Gateway import/health
postflight. One-file staging, Gitlink, symlink escape, alternates, missing
objects, source drift, caller path, network/follow-main, missing predecessor,
stale/rehashed receipt, fence conflict, lost-ack replay, wrong service
identity, or failed authenticated postflight fails closed with zero effect.

## Objective and authority boundary

Implement the smallest typed contract and single-manager behavior for a
manager-owned, content-addressed desired Gateway deployment and exact
predecessor, with physical reconciliation semantics ready for a later host
canary. This Card authorizes source implementation only. It authorizes no
filesystem/process/launchd/Gateway/DevSpace/OAuth/runtime effect, host receipt,
stable-manager installation, adoption, rollback drill, merge, release or
production claim.

The one public operation/effect class introduced by R1 is:

- operation: `gateway-recover`
- effect class: `GATEWAY_DURABLE_RECOVERY`

`reconcile` is an internal, read-only continuation of the same request,
receipt, idempotency fence and ledger chain after `UNCERTAIN_EFFECT`. It is
not a public operation, a new effect class, a second receipt, or a second
authority surface. The existing three-child host bundle is historical and is
not reused or widened.

The worker may create one source Candidate in exactly the four allowed files.
Card/INDEX creation and later acceptance are coordinator-owned. `AUTO_CHAIN` is
false; the worker must stop after its bounded Candidate and report the exact
files, tests and claim ceiling.

## Contract requirements

In `nexus/contracts/gateway_deployment.py`, preserve the pure/no-I/O contract
module and add strict hashable records/enums:

1. `DeploymentManifest`: manager-issued deployment ID, repository, commit,
   tree, role, `source_set_sha256`, fixed tracked entrypoint path/blob/hash/mode,
   interpreter identity/hash, and canonical manifest/deployment hash. It
   contains no raw bundle hash or caller-selected root, label, PID, plist,
   command, port, symlink or follow-main selector.
2. `RecoverySourceSet`: the canonical semantic accepted/desired/predecessor,
   entrypoint, and interpreter identity described above. The manager recomputes
   it; callers cannot supply or select any constituent ref or path.
3. `SourceBundleEvidence`: strict post-receipt physical evidence for the exact
   three named heads, raw bundle bytes, verified bare store, and request/fence.
   It is ledger evidence only and is never accepted as authority.
4. Readiness classifications exactly covering `TARGET_READY`,
   `ROLLBACK_READY`, and `ROLLBACK_UNAVAILABLE`; readiness requires verified
   materialized bytes plus manifest, ancestry, ownership/mode and fixed
   identities, never metadata alone.
5. A typed reconcile outcome that records request/hash/fence, desired and
   predecessor manifest IDs, physical observation, effect-started flag, result
   (`VERIFIED`, `ROLLED_BACK`, `BLOCKED`, or `UNCERTAIN_EFFECT`) and evidence
   hash. It must model reconcile as continuation of the same request.
6. Add `EFFECT_STARTED` to the state vocabulary and
   `GATEWAY_DURABLE_RECOVERY` to the effect vocabulary. Do not add
   `RECONCILE` as an effect class. Existing `STARTED` ledger records remain
   parseable as historical records.
7. Extend the typed request so desired/predecessor manifests and readiness,
   operation `gateway-recover`, and the same host receipt/fence are included
   in canonical request hashing and CAS checks.

## Manager requirements

In `scripts/ops/mcp_gateway_durable.py`, retain the sole process/effect owner,
fixed Gateway label/plist/endpoint, inter-process lock, ledger parent-hash
chain, request hash, idempotency fence, CAS and authenticated postflight.
Define one fixed manager-owned deployment root beneath the existing Gateway
state boundary:

`/Users/jameschen/Library/Application Support/Nexus/gateway-direct/deployments`

The exact path is a manager constant. A profile/deployment ID selects a
deployment; no caller path exists. Staging must atomically materialize desired
and predecessor bytes into content-addressed directories, reject symlinked or
unsafe ancestry, and verify repository, commit/tree, entrypoint, interpreter,
owner, mode and canonical bytes. The launchd plist is rendered solely from
fixed manager literals plus the verified staged deployment.

Required order:

1. Parse and validate the exact request, authority binding, lock, ledger tail,
   CAS and static source/interpreter/plist constraints.
2. Recompute the semantic source set and both manager-derived manifests; they
   must equal the receipt/request expectations. Then build/verify the exact
   three-role bundle, compute raw bundle SHA-256, import it into and verify the
   strict fixed bare repository, and persist `SourceBundleEvidence` before any
   worktree promotion.
3. Stage desired bytes and append `TARGET_READY`.
4. Stage exact predecessor bytes and append `ROLLBACK_READY`. Missing bytes or
   metadata-only predecessor yields `ROLLBACK_UNAVAILABLE` and `BLOCKED` with
   zero process effect.
5. Persist request, both manifests and static evidence; append
   `EFFECT_STARTED` while holding the lock immediately before the one fixed
   recovery effect.
6. Execute only the manager-selected fixed service effect. No generic shell,
   launchctl, PID, label, plist, command, environment, port, root or DevSpace
   argument is accepted.
7. Re-observe fixed label/PID/start identity/listener/plist/manifest, then run
   authenticated `/health`, `initialize` and `tools/list`. Only exact desired
   identity reaches `VERIFIED`.
8. On timeout, disconnect, crash or lost acknowledgement, append
   `UNCERTAIN_EFFECT` and internally reconcile the same request/fence before
   retry. Desired serving plus complete postflight completes the original
   request; predecessor serving records `ROLLED_BACK`; neither provable remains
   uncertain/blocked. Never start a second Gateway blindly.

A healthy already-desired deployment is an idempotent no-op. The historical
ephemeral profiles and three-effect host bundle are not redesigned authority.

## State machine

| State | Entry | Allowed next | Effect |
|---|---|---|---|
| `REQUESTED` | strict request/hash/fence parsed | `PREFLIGHTED`, `BLOCKED` | none |
| `PREFLIGHTED` | static authority/lock/CAS gates pass | `TARGET_READY`, `BLOCKED` | none |
| `TARGET_READY` | desired bytes and manifest verified | `ROLLBACK_READY`, `ROLLBACK_UNAVAILABLE`, `BLOCKED` | none |
| `ROLLBACK_READY` | predecessor bytes/plist/manifest verified | `EFFECT_STARTED`, `BLOCKED` | none |
| `ROLLBACK_UNAVAILABLE` | predecessor not reconstructable | `BLOCKED` | forbidden |
| `EFFECT_STARTED` | ledger persisted immediately before effect | `SERVICE_OBSERVED`, `UNCERTAIN_EFFECT` | one fixed effect |
| `SERVICE_OBSERVED` | fixed physical service identity observed | `IDENTITY_VERIFIED`, `UNCERTAIN_EFFECT` | none |
| `IDENTITY_VERIFIED` | manifest/runtime identity exact | `CLIENT_BOUND`, `UNCERTAIN_EFFECT` | none |
| `CLIENT_BOUND` | authenticated client binding succeeds | `VERIFIED`, `UNCERTAIN_EFFECT` | none |
| `UNCERTAIN_EFFECT` | lost ack/timeout/crash/postflight mismatch | `SERVICE_OBSERVED`, `ROLLED_BACK`, `BLOCKED`, or remain uncertain | no blind retry and no second `EFFECT_STARTED` |
| `ROLLED_BACK` | exact predecessor serving and verified | terminal | none |
| `VERIFIED` | desired and complete postflight verified | terminal | none |
| `BLOCKED` | any failed gate/unprovable identity | terminal | none |

No transition from `ROLLBACK_UNAVAILABLE` reaches an effect. Internal
reconcile never changes the receipt/effect class and never creates a second
authority record.

For an already-desired service, `EFFECT_STARTED` means the fixed adoption seam
was durably entered, not that an external mutation occurred. The fixed adapter
must perform a final observation, return an acknowledgement with
`applied=false` and `already_desired=true`, make zero plist/launchctl writes,
and continue through `SERVICE_OBSERVED -> IDENTITY_VERIFIED -> CLIENT_BOUND ->
VERIFIED`. Replays from `EFFECT_STARTED` or `UNCERTAIN_EFFECT` reconcile
physical identity only and can never append or invoke a second
`EFFECT_STARTED` effect.

## TDD RED-first and required tests

Before implementation, add focused RED tests in the two allowed test files and
run them so they fail for the intended missing R1 contract/manager behavior.
The RED run must be recorded in the worker report; do not manufacture a TDD
history if the test did not execute. Then implement the smallest change,
rerun GREEN, and only afterward run the broader suite.

Tests must cover typed strict parsing/hash and transition rejection, fixed
`gateway-recover` pairing, content-addressed desired/predecessor staging,
readiness gates, zero-effect preflight failures, missing predecessor, tamper,
ownership/mode/symlink/ancestry, caller-surface rejection, idempotency/CAS,
concurrent identical calls, lost acknowledgement, physical reconciliation,
wrong postflight identity, authenticated health/initialize/tools-list, and
already-desired no-op. Fake runners must assert exact calls and zero launchctl
calls before `EFFECT_STARTED`.

## Negative controls

- Failing health observer or missing disposable current root cannot block static
  staging and cannot be called before `TARGET_READY`/`ROLLBACK_READY`.
- Missing predecessor bytes or cached metadata alone returns
  `ROLLBACK_UNAVAILABLE` and performs zero process effects.
- Dirty/tampered/hash-mismatched/symlinked/wrong-owner/wrong-mode deployment
  material blocks before destination write or launchctl.
- Caller-selected root, label, PID, plist, command, port, environment,
  follow-main or DevSpace path is rejected before observation.
- Conflicting request/hash/fence fails CAS; duplicate same request is one
  effect; replayed `EFFECT_STARTED`/`UNCERTAIN_EFFECT` reconciles, never starts
  a second Gateway.
- Wrong root/HEAD/tree/manifest/schema/permission identity, post-effect health
  timeout, initialize/tools-list failure or listener mismatch never verifies.
- Deployment ancestry/content hash/manifest tamper fails closed; DevSpace and
  unrelated services remain untouched; no second manager is introduced.
- No semantic identity builder accepts raw bundle hash, receipt hash, or
  observed fresh-main SHA. Byte-different valid bundle encodings of the same
  exact semantic source set produce the same deployment IDs but distinct
  physical evidence. Wrong source-set field, named-ref role, object set,
  persisted bundle hash, or head map fails closed.

## Verification and exit

Required on the implementation branch:

```sh
git diff --check
python -m pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
python -m pytest -q tests/contracts/test_gateway_deployment_contract.py -k 'manifest or readiness or transition or recover'
python -m pytest -q tests/ops/test_mcp_gateway_durable.py -k 'stage or recover or rollback or lost_ack or caller_selected or launchctl'
rg -n 'TARGET_READY|ROLLBACK_READY|ROLLBACK_UNAVAILABLE|EFFECT_STARTED|UNCERTAIN_EFFECT|GATEWAY_DURABLE_RECOVERY|gateway-recover' nexus/contracts/gateway_deployment.py scripts/ops/mcp_gateway_durable.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
git diff --name-only
```

The name-only output must contain no more than the exact four allowed files;
inspect staged/tracked deletions and the complete diff. Source acceptance is
independent coordinator verification. No host command, launchctl, Gateway,
OAuth or runtime probe is a source verifier.

## Fresh host boundary and dependencies

R1 source acceptance must bind the exact post-merge current-main SHA/tree,
final manager hash, independent acceptance receipt and source Card hash. Only
after that may the coordinator issue a fresh, separately reviewed host receipt
for `gateway-recover` / `GATEWAY_DURABLE_RECOVERY`. The receipt must bind fixed
label/plist/endpoint, desired and predecessor manifest hashes, request/fence,
validity and revocation state. It must require both readiness gates before any
effect and preserve authenticated postflight and rollback/reconcile evidence.

The existing `nexus.gateway.host_effect_authority_bundle.v1` and its historical
three children cannot be reused, widened, relabeled or copied into this
authority. Source Candidate, source acceptance, host receipt, staging,
adoption, canary and Issue #526 closure remain distinct states. No DevSpace or
ChatGPT-facing action is part of R1; `SERIALIZE_AFTER:#398` remains in force.

## Maximum claim

`NEXUS_GATEWAY_R1_SOURCE_CANDIDATE_ONLY`

The worker may claim only a four-file source Candidate with executed tests and
diff evidence. It may not claim source acceptance, merge, host authority,
staging, adoption, Gateway recovery, local canary, Issue #526 closure,
production readiness or public readiness.

`AUTO_CHAIN=false`

`STOPPED_AFTER_BOUNDED_TASK`
