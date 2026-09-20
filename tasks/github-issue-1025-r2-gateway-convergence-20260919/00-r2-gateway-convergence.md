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
- commit: `c6e2609f9c148e42d96eaf9e1e9cfddb0579ad33`
- tree: `7fd8be2eb8b20a81d9279aa7bb4400a7fdedeef6`
- source PR #1022 exact head: `49b1f32e3cbc131f272422f9c47817f7d35022f0`
- source PR head tree: `21cca6f65620ab328b30e97d80f14e108d18df0e`
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
- desired commit/tree `c6e2609f... / 7fd8be2e...`;
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
3. fresh recovery-authority Candidate is exact, current-target-bound, and merged;
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

- current Nexus-new main: `c6e2609f9c148e42d96eaf9e1e9cfddb0579ad33`
- current tree: `7fd8be2eb8b20a81d9279aa7bb4400a7fdedeef6`
- valid governed B1 reintegration is an ancestor of this exact main;
- drift from B1-valid main `354a496d315e2d55c23aadb58175f1b6356c330c` to this target changes only `nexus/health/executor.py`, `nexus/health/sandbox.py`, and `tests/health/test_sandbox_safety.py`;
- that drift has no path overlap with the Gateway entrypoint, B1 tool-authority contract, B3 Task Card, or the runtime dependency pin;
- Gateway entrypoint blob remains `f6d0131df01c60b055a8eeec1be2125705c590f3`;
- current `pyproject.toml` still pins `nexus-runtime@632e1a18d164d7dadf6bb98caa9c4e9d17c436f3`;
- B1 contract blob remains `5789cc0ac74e5c08a33fb89c0ef9c0c7e043fed7`;
- B3 Task Card blob remains `a3187e24964c0f86f60cf3cd1b75a8d959a96cb8`;
- physical predecessor remains loaded Gateway source `db57b1e44715e83bd1aea1c5f81ff058b2745782`.

The historical `5c38bfddb34ded0db841dec32101ba724b1cc4ac` merge is incident lineage, not the desired runtime target. This rebind does not change production behavior, provider/model selection, G4 scope, release authority, or production claims. #526 remains the sole Gateway host-effect mechanism.

## 2026-09-20 current transport-manager compatibility rebind delta

This bounded delta supersedes only the frozen recovery-manager generation for the current R2 attempt. It does not widen the desired Gateway source, predecessor, runtime package, process authority, or claim ceiling.

Fresh evidence after the later DevSpace cutover:

- collaboration main at the rebind freeze: `295536811ff563354da31022b09c799e910f2c9e / e9f7c0d7162fc597c05c72afce798c312c69251c`;
- loaded Gateway predecessor remains `db57b1e44715e83bd1aea1c5f81ff058b2745782 / e2f801d7e7cb6a94383949a8c8dff9dff151fe8d`;
- desired Gateway remains `c6e2609f9c148e42d96eaf9e1e9cfddb0579ad33 / 7fd8be2eb8b20a81d9279aa7bb4400a7fdedeef6`;
- fixed interpreter remains converged to `nexus-runtime@632e1a18d164d7dadf6bb98caa9c4e9d17c436f3`;
- current DevSpace typed recovery bridge accepts manager SHA-256 `6873dde17e08d4020620c2408e414327b176be723f5f23f01bee754b2627502c`;
- the same bridge accepts Gateway deployment-contract SHA-256 `3cd032639f69349bd44e61dec41551957e9034157febfff83e7fb3c89b5ef798`;
- the A2 fixed manager `3f0c3420...` is therefore transport-incompatible before effect, and the bridge correctly fails closed;
- `6873dde1...` is the exact manager from accepted source merge `4306e223f4fc1a092f7a0a21ff4aa5da4455f97e` / Candidate `b0ec2fc4993bb2c2d49d5c66e510e2a13f89a940`;
- that exact Candidate had terminal-success GitHub exact-head Pyright, Governance, Ruff, Bandit, Secret Audit, and Pytest checks;
- Owner source-verification payload SHA-256 `df0f8db214e508bb49a1128411f7ecd98d593951e1dfee9aed255a0bdfe082e3` binds the same `b0ec2fc...` commit/tree and successful check set;
- the historical continuation authority that referenced `6873dde1...` is expired and is evidence only; it is not reused as current effect authority.

Current Owner activation:

- Issue #1025 comment `5747735968`;
- exact Owner message SHA-256 `ab7212e8e7c5e8cbf7f2c7b13dd28fd7eda2bca0ccd5e1f8310139d407ce4df2`;
- activation id `BREAK_GLASS_ISSUE1025_R2_MANAGER_REBIND_20260920_A3`.

The A3 recovery receipt must therefore:

1. bind current issuance floor `295536811... / e9f7c0d7...`;
2. keep desired and predecessor semantic identities unchanged;
3. bind manager `6873dde1...` and verification lineage `df0f8db2...`;
4. use a new receipt/request/idempotency fence and bounded freshness;
5. remain future-tracked external-bootstrap provenance with no standing-grant substitution.

After the A3 Candidate is independently verified and integrated, the host step may materialize only the exact tracked A3 receipt/request plus the exact `6873dde1...` manager bytes from accepted source `4306e223...`. Typed zero-effect recovery preflight must return the expected `BLOCKED` checkpoint with `TARGET_READY` and `ROLLBACK_READY` before any Gateway replacement effect is permitted.

No historical continuation authority is revived. No second process owner, alternate recovery lifecycle, generic host command, #1032/B3 effect, G4, release, or public-production claim is authorized.

`AUTO_CHAIN=false`.

## 2026-09-20 live DevSpace manager evidence correction (A4)

This corrective delta supersedes only the A3 manager-generation inference introduced by PR #1035. It preserves the R2 desired/predecessor/runtime target and the #526 single process/effect owner.

Authoritative runtime evidence:

- live DevSpace source: `903922900665ed7519f98828bac74cd62e72ebd4`;
- live DevSpace build: `devspace-1.0.7-90392290`;
- cutover: `closed / normal / reconciliationRequired=false`;
- exact live `src/durable-operations.ts@90392290...` accepts manager SHA-256 `3f0c34204bef175fcfad7150c5919d96f6b3735813cea5258bdcd51e37d4baeb`;
- the same live source accepts deployment-contract SHA-256 `3cd032639f69349bd44e61dec41551957e9034157febfff83e7fb3c89b5ef798`;
- the local checkout that exposed `6873dde1...` was not the live DevSpace source (`03841ac7...`);
- current Nexus-new main at correction freeze is `482fb4b83d8ac9b5ceb33b0e3f9890634f0da897 / 85a8a14a6a64cecced02f26be96c78f696b6ff47`;
- current Nexus-new manager bytes are exactly `3f0c3420...`;
- existing independent acceptance lineage for that manager is `3e1ed6a7c05d2951ab343e4b249425bfdbd0203dcdd4e11b0f7cdbe5342b2bd1`;
- A3 typed preflight failed before manager execution with `effect_started=false`; no A3 Gateway replacement effect occurred.

Corrective Owner activation: Issue #1025 comment `5747996106`.
Exact Owner instruction hash remains `ab7212e8e7c5e8cbf7f2c7b13dd28fd7eda2bca0ccd5e1f8310139d407ce4df2`.

A4 must bind:

- issuance floor `482fb4b8... / 85a8a14a...`;
- manager `3f0c3420...`;
- independent manager acceptance `3e1ed6a7...`;
- desired `c6e2609f... / 7fd8be2e...`;
- predecessor `db57b1e4... / e2f801d...`;
- fresh receipt/request/fence identities;
- bounded expiry;
- future-tracked external-bootstrap provenance.

PR #1035 remains historical evidence of a corrected false inference and grants no future host effect. After A4 integration, only the exact tracked A4 receipt/request and `3f0c3420...` manager may be materialized for typed zero-effect preflight.

`AUTO_CHAIN=false`.
