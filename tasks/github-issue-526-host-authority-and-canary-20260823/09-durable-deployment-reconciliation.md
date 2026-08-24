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
   tree, fixed entrypoint and hash, interpreter identity/hash, canonical
   manifest/content hash, owner and mode. It contains no caller-selected root,
   label, PID, plist, command, port, symlink or follow-main selector.
2. Readiness classifications exactly covering `TARGET_READY`,
   `ROLLBACK_READY`, and `ROLLBACK_UNAVAILABLE`; readiness requires verified
   materialized bytes plus manifest, ancestry, ownership/mode and fixed
   identities, never metadata alone.
3. A typed reconcile outcome that records request/hash/fence, desired and
   predecessor manifest IDs, physical observation, effect-started flag, result
   (`VERIFIED`, `ROLLED_BACK`, `BLOCKED`, or `UNCERTAIN_EFFECT`) and evidence
   hash. It must model reconcile as continuation of the same request.
4. Add `EFFECT_STARTED` to the state vocabulary and
   `GATEWAY_DURABLE_RECOVERY` to the effect vocabulary. Do not add
   `RECONCILE` as an effect class. Existing `STARTED` ledger records remain
   parseable as historical records.
5. Extend the typed request so desired/predecessor manifests and readiness,
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
2. Stage desired bytes and append `TARGET_READY`.
3. Stage exact predecessor bytes and append `ROLLBACK_READY`. Missing bytes or
   metadata-only predecessor yields `ROLLBACK_UNAVAILABLE` and `BLOCKED` with
   zero process effect.
4. Persist request, both manifests and static evidence; append
   `EFFECT_STARTED` while holding the lock immediately before the one fixed
   recovery effect.
5. Execute only the manager-selected fixed service effect. No generic shell,
   launchctl, PID, label, plist, command, environment, port, root or DevSpace
   argument is accepted.
6. Re-observe fixed label/PID/start identity/listener/plist/manifest, then run
   authenticated `/health`, `initialize` and `tools/list`. Only exact desired
   identity reaches `VERIFIED`.
7. On timeout, disconnect, crash or lost acknowledgement, append
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
| `TARGET_READY` | desired bytes and manifest verified | `ROLLBACK_READY`, `BLOCKED` | none |
| `ROLLBACK_READY` | predecessor bytes/plist/manifest verified | `EFFECT_STARTED`, `BLOCKED` | none |
| `ROLLBACK_UNAVAILABLE` | predecessor not reconstructable | `BLOCKED` | forbidden |
| `EFFECT_STARTED` | ledger persisted immediately before effect | `SERVICE_OBSERVED`, `UNCERTAIN_EFFECT` | one fixed effect |
| `SERVICE_OBSERVED` | fixed physical service identity observed | `IDENTITY_VERIFIED`, `UNCERTAIN_EFFECT` | none |
| `IDENTITY_VERIFIED` | manifest/runtime identity exact | `CLIENT_BOUND`, `UNCERTAIN_EFFECT` | none |
| `CLIENT_BOUND` | authenticated client binding succeeds | `VERIFIED`, `UNCERTAIN_EFFECT` | none |
| `UNCERTAIN_EFFECT` | lost ack/timeout/crash/postflight mismatch | internal reconcile to `VERIFIED`, `ROLLED_BACK`, `BLOCKED`, or remain uncertain | no blind retry |
| `ROLLED_BACK` | exact predecessor serving and verified | terminal | none |
| `VERIFIED` | desired and complete postflight verified | terminal | none |
| `BLOCKED` | any failed gate/unprovable identity | terminal | none |

No transition from `ROLLBACK_UNAVAILABLE` reaches an effect. Internal
reconcile never changes the receipt/effect class and never creates a second
authority record.

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
