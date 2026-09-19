# Task Card: Issue #1025 R2 — Gateway runtime convergence

artifact_authority: current
task_id: `issue-1025-r2-gateway-convergence-20260919`
owner: James Chen
status: ACTIVE
contract_kind: TRACKED_TASK_CARD
execution_lane: GOVERNED
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Objective

Converge the loaded ChatGPT-facing Nexus Gateway from the physically observed stale deployment to the exact current source generation that contains R1 Wave 4 effect-authority enforcement.

Reuse the existing #526 durable Gateway recovery manager and lifecycle. Do not create another process manager, deployment authority, or runtime source of truth.

## Owner authority

Durable owner: `James3014/Nexus-new#1025`.

The Owner instructed the coordinator to continue the previously described R2 runtime-convergence work. Issue #1025 freezes that bounded activation and its non-goals.

Issue-body SHA-256 at this Task Card bootstrap:

`193aa33915f6da4478f267312a6ef21f438e4baba5d53f172b551de6e40b8a57`

## Frozen source fence

Desired Nexus-new:
- commit: `354a496d315e2d55c23aadb58175f1b6356c330c`
- tree: `a70f34af9f07553d296572effe69e112172a46fa`
- source PR #1022 exact head: `49b1f32e3cbc131f272422f9c47817f7d35022f0`
- source PR head tree: `a70f34af9f07553d296572effe69e112172a46fa`
- PR #1022 exact-head required workflows: terminal success

Desired Gateway entrypoint:
- path: `scripts/ops/nexus_mcp_gateway_http.py`
- blob: `f6d0131df01c60b055a8eeec1be2125705c590f3`
- SHA-256: `8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1`

Current durable manager:
- path: `scripts/ops/mcp_gateway_durable.py`
- SHA-256: `3f0c34204bef175fcfad7150c5919d96f6b3735813cea5258bdcd51e37d4baeb`
- this exact manager hash is already bound by the current #526 authority lineage to independent acceptance hash `3e1ed6a7c05d2951ab343e4b249425bfdbd0203dcdd4e11b0f7cdbe5342b2bd1`

## R2-A live runtime evidence

Physically observed running Gateway:
- loaded commit: `db57b1e44715e83bd1aea1c5f81ff058b2745782`
- loaded tree: `e2f801d7e7cb6a94383949a8c8dff9dff151fe8d`
- deployment id: `r1-1a08a8184a51c8b8edadfc09891036fffcab8ec4`
- Gateway upstream freshness: `STALE`
- fixed interpreter path: `/Users/jameschen/Workspace/Nexus-new/.venv/bin/python`
- installed/imported `nexus-runtime`: `b48fbd7abe96041bffcea31fa31fa90e78582f02`
- desired source pins `nexus-runtime@632e1a18d164d7dadf6bb98caa9c4e9d17c436f3`
- loaded deployment predates R1 and lacks `code_integrity_verifier.py` plus the CapabilityGate authority-boundary marker

R2-A disposition:

`SOURCE_AHEAD_OF_RUNTIME`

## Dependency convergence invariant

Source cutover alone is insufficient.

The old runtime coordinator at `b48fbd7a...` contains no effect-authorization/tool-projection enforcement. The desired `632e1a18...` runtime adds runtime-owned `EffectAuthorization`, `ToolProjectionManifest`, durable authorization/projection binding, and forwards those exact artifacts to the worker boundary.

Both runtime revisions declare the same package dependencies:
- `PyYAML>=6`
- `nexus-learning>=0.1.0`

Therefore the minimum package-environment change is the exact replacement of `nexus-runtime` in the fixed Gateway interpreter environment. Do not churn unrelated dependencies.

Before any Gateway reload:
1. install/synchronize exactly `nexus-runtime@632e1a18d164d7dadf6bb98caa9c4e9d17c436f3` into the fixed Gateway interpreter environment;
2. read back the installed direct-url/revision;
3. import the runtime-owned effect-authorization/projection symbols from that interpreter;
4. fail closed if exact identity/API readback does not match.

This package operation may change the interpreter environment only. It must not reset, stash, clean, rebase, commit, or otherwise mutate Git source in the dirty/diverged `/Users/jameschen/Workspace/Nexus-new` checkout.

## Canonical recovery mechanism

Only this host-effect chain is authorized:

`Dev MCP fixed typed #526 recovery transport -> scripts/ops/mcp_gateway_durable.py -> exact deployment/restart -> physical readback`

DevSpace is transport, not process authority. #526 remains the sole Gateway recovery process/effect owner.

Do not use generic launchctl/plist/PID manipulation.

## Allowed repository mutation after this Card is merged

Maximum repository mutation surface:
- `tasks/github-issue-1025-r2-gateway-convergence-20260919/00-r2-gateway-convergence.md`
- `tasks/github-issue-1025-r2-gateway-convergence-20260919/INDEX.md`
- at most one bounded R2 acceptance/evidence JSON under the same Task directory, only if needed to bind current evidence truthfully;
- existing #526 recovery authority receipt:
  `tasks/github-issue-526-g20-r1-source-contract-delta-20260903/02-r1-complete-deployment-recovery-authority-receipt.json`

No production/runtime source-code change is authorized.
No deletion is authorized.

## Fresh recovery authority requirements

The new tracked receipt must bind:
- Issue #1025 and this Task Card as execution authority lineage;
- desired commit/tree `5c38bfdd... / 21cca6f6...`;
- predecessor commit/tree `db57b1e4... / e2f801d7...`;
- exact manager SHA-256 `3f0c3420...`;
- current accepted manager lineage `3e1ed6a7...`;
- exact fixed interpreter identity;
- self-contained predecessor Git bundle hash, positive size, and fixed predecessor ref;
- manager-derived desired/predecessor manifests;
- fresh receipt/request/idempotency-fence identities;
- Owner activation from #1025;
- bounded freshness and revocation semantics;
- existing standing coordinator grant only where its current contract permits;
- `operation=gateway-recover`;
- `effect_class=GATEWAY_DURABLE_RECOVERY`.

The canonical #526 host-card identity remains the manager's semantic recovery contract; this R2 Card authorizes creation/use of a fresh instance of that existing mechanism and does not replace it.

## Host-effect gate

Before first reload/rebind effect:
1. this Card/INDEX are Git-tracked and current;
2. package-environment convergence is exact and read back;
3. fresh recovery-authority Candidate is exact and merged;
4. current main and authority bytes are re-read;
5. required authority bytes are materialized byte-exact into the fixed #526 state root;
6. predecessor artifact passes manager hash/size/mode/owner/self-contained verification;
7. typed `nexus_gateway_recovery_preflight` passes with zero effect;
8. active/uncertain work and quiescence are re-read;
9. observed Gateway still matches the frozen predecessor.

Only then may `nexus_gateway_recover` execute.

Unknown/timeout outcome must reconcile the same operation. Never create a wider retry.

## R2 completion evidence

R2 succeeds only after physical postflight proves:
- Gateway loaded desired commit/tree;
- fixed interpreter imports exact `nexus-runtime@632e1a18...`;
- runtime exposes `EffectAuthorization` / `ToolProjectionManifest`;
- loaded Nexus-new source contains `code_integrity_v1` and the CapabilityGate non-authority marker;
- replacement server identity is coherent;
- tool manifest/schema/permission/lifecycle surfaces are valid for the desired deployment;
- #526 durable recovery ledger reaches a truthful terminal state;
- exact replay does not duplicate the replacement effect;
- unrelated DevSpace service/workspaces are unchanged.

## Non-goals

- no R3 hostile cross-repository E2E;
- no new process manager or recovery lifecycle;
- no direct manual launchctl/plist manipulation;
- no Git-source mutation in the existing dirty/diverged Nexus-new checkout;
- no CapabilityPlanner, Workforce, or nexus-core semantic change;
- no release/public production-readiness claim;
- no automatic successor work.

## Claim ceiling

Before physical convergence:

`R2_ACTIVATION_AUTHORITY_CANDIDATE_ONLY`

After successful exact host readback:

`R2_GATEWAY_RUNTIME_CONVERGENCE_VERIFIED`

This does not establish R3 hostile effect-authority E2E.

## Exit criterion

R2 is terminal only when the desired source generation and exact runtime package generation are both physically loaded and read back through the current Gateway, with the #526 recovery ledger reconciled and no unauthorized side effect.

Then STOP. `AUTO_CHAIN=false`.


## 2026-09-19 current-target rebind delta

This bounded recovery delta supersedes only the frozen desired Nexus-new source identity above.

Fresh canonical evidence:

- current Nexus-new main: `354a496d315e2d55c23aadb58175f1b6356c330c`
- current tree: `a70f34af9f07553d296572effe69e112172a46fa`
- the valid governed B1 reintegration is present on this exact main;
- compare `5c38bfddb34ded0db841dec32101ba724b1cc4ac..354a496d315e2d55c23aadb58175f1b6356c330c` changes only this R2 Task Card and its INDEX; no production source file differs;
- Gateway entrypoint blob remains `f6d0131df01c60b055a8eeec1be2125705c590f3`;
- the exact Gateway entrypoint bytes remain SHA-256 `8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1`;
- current `pyproject.toml` still pins `nexus-runtime@632e1a18d164d7dadf6bb98caa9c4e9d17c436f3`;
- physical predecessor remains loaded Gateway source `db57b1e44715e83bd1aea1c5f81ff058b2745782`.

Reason for rebind:

The historical `5c38bfddb34ded0db841dec32101ba724b1cc4ac` merge was later treated as invalid-authority incident lineage and was recovered/re-integrated under valid governed authority. Runtime recovery must therefore target the current valid canonical commit, not the historical incident commit, even though the relevant production source bytes are equivalent.

This delta does not authorize any new source behavior, process manager, provider/model choice, G4 work, release, or production-readiness claim. The existing #526 durable Gateway recovery mechanism remains the sole host-effect path.
