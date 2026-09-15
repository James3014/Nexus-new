# TASK-526-J-R1-LIVE-HOST-ADAPTER — Bind the R1 recovery state machine to one fixed real Gateway host adapter

```yaml
task_id: TASK-526-J-R1-LIVE-HOST-ADAPTER
issue: 526
repository: James3014/Nexus-new
status: ACTIVE
base_main: 4bfdae78ede40294d1402470b5487660ed3d4c21
base_tree: b00863aca63bf017289ee467f6d6a6d818d61315
auto_chain: false
claim_mode: MANUAL_DISPATCH
claim_ceiling: NEXUS_GATEWAY_R1_LIVE_HOST_ADAPTER_SOURCE_CANDIDATE_ONLY
owner_authorization_comment: 5418927784
```

## Authority and evidence basis

Issue #526 remains the governing Ready control-plane repair. Owner authorization comment `5418927784` authorizes the exact TASK-002 Gateway rebind target `b2a9cca573580d2edbd5531bb9e4bf92479e0e3a` / tree `747d9dcecd47dff3d063e7948496d8adb33f50bc`, with exact predecessor `3d28fa7b65df30e207e53de7caadf93a2b7a8fc0` / tree `5e6476b2b12211e7cdcfe9294942b633ffbcef59`, Gateway-only effect, rollback, and authenticated post-reload identity proof. It explicitly forbids DevSpace or unrelated-service mutation.

PR #594 merged the activation-lineage gate. PR #595 merged the fresh recovery authority receipt. Fresh read-only falsification then proved three same-contract source gaps before any host effect was attempted:

1. `_gateway_recover_with_adapters(...)` owns the R1 crash/reconcile state machine, but no production `_RecoveryAdapters` implementation exists; all concrete adapters are test-only.
2. `_recovery_expected_postflight(...)` currently synthesizes manifest/schema/permission hashes that do not equal the real Gateway identities. Desired source `b2a9cca...` deterministically reports tool manifest `24773501ac038027a69a967b1db135648d6af4d997ba417ebb9b7df4c34709d5`, full schema `d9ae8978040f83d476ded53abc4f3dea58216d18f0bd1e7272c3efd8c5eecee7`, permission policy `45910e1e37069abf3d5b01f15196548da094e2fc6b71cf8a6136e8cdf9fd71cf`, lifecycle `nexus.lifecycle.gateway.v2`, and 29 tools.
3. `_recovery_expected_plist_bytes(...)` places literal `FIXED_SECRET_STORE_REFERENCE` in `NEXUS_MCP_GATEWAY_TOKEN`; a real desired process launched from that plist cannot authenticate. The already-accepted `_gateway_plist` / `_gateway_wrapper_command` path instead sources only the fixed `mcp-gateway.env` and must be reused.

These are source defects inside the already-approved #526 recovery design, not new product semantics. This Card is source-only. It authorizes no receipt issuance, local authority-store materialization, manager installation, launchctl/process effect, Gateway reload, DevSpace/OAuth mutation, merge, release, or production claim.

## Exact mutation scope

Modify only:

- `scripts/ops/mcp_gateway_durable.py`
- `tests/ops/test_mcp_gateway_durable.py`

Create/delete none. Do not edit `nexus/contracts/gateway_deployment.py`, Task Cards/INDEX, HTTP/stdio Gateway source, DevSpace, OAuth, route/Planner/Workforce policy, lifecycle state, receipts, local application state, LaunchAgents, or unrelated formatting.

## Required behavior

### J1 — preserve the public effect-free checkpoint

`gateway_recover(request)` and the existing public CLI action `gateway-recover` remain effect-free staging/checkpoint operations. Existing negative tests proving that this public path cannot call launchctl/exec or inject adapters must remain green.

Add a distinct manager-local host adapter entry seam for the same typed `GatewayRecoveryRequest` / `GATEWAY_DURABLE_RECOVERY` request. It is not a new MCP operation or effect class. The seam must have no caller-selected executable, label, plist, PID, endpoint, source root, environment, service, DevSpace path, or command. It may consume only the fixed manager stores/constants and the request/receipt/manifests already validated by R1.

A future narrow DevSpace transport may invoke this seam, but this Card does not implement or modify that transport.

### J2 — real fixed wrapper plist

For R1 desired and predecessor deployment roots, derive plist bytes only from fixed manager literals plus the manager-derived deployment root and fixed Gateway entrypoint. Reuse `_gateway_wrapper_command` semantics so the process sources only fixed `ENV_PATH`, exports the fixed canonical source root and self-hosted state directory, and execs the fixed interpreter/entrypoint.

Do not place token bytes, placeholders, caller environment, or arbitrary shell text in the plist. The generated plist must remain fixed-label `com.nexus.mcp.gateway.direct`, fixed logs, `RunAtLoad=true`, `KeepAlive=true`, and exact WorkingDirectory.

`_recovery_expected_plist_sha256(...)` and physical classification must use those same bytes.

### J3 — one production adapter over the existing R1 state machine

Implement the smallest fixed production `_RecoveryAdapters` factory/seams required by `_gateway_recover_with_adapters(...)`:

- **effect**: under the existing R1 effect ownership/ledger transition, adopt an already-desired service as an idempotent no-op or replace only fixed `com.nexus.mcp.gateway.direct`. Write only the fixed Gateway plist. Use only fixed `launchctl bootout gui/<uid>/com.nexus.mcp.gateway.direct` and `launchctl bootstrap gui/<uid> <fixed plist>`. Never touch DevSpace or another label. If desired activation fails after the old service is removed, attempt only the exact staged predecessor restoration before returning uncertainty; never start a second competing Gateway blindly.
- **observe**: observe only the fixed label/listener/plist and resolve the running source only when it equals the exact manager-derived desired or predecessor deployment root. Re-read exact Git HEAD/tree/clean state, plist hash, PID/start identity, loopback listener, and authenticated Gateway server instance. Unknown/mixed identity remains unclassified/fail-closed.
- **postflight**: bearer-authenticate through the fixed secret env and fixed loopback endpoint, call `/health`, MCP `initialize`, and `tools/list`, normalize the actual Gateway identity fields, recompute the sorted tool-manifest and full tool-schema hashes, and require exact root/HEAD/tree/server instance/lifecycle/permission/tool/schema identity for the staged desired deployment. Do not use synthetic recovery hashes.

Reuse existing accepted helpers where semantics are identical (`_http_json`, wrapper construction, manifest/schema recomputation/normalization concepts, fixed launchctl handling). Do not create a second process manager, second ledger, second authority store, or second route/Planner.

### J4 — exact desired runtime identity derives from desired source, not current live runtime

Postflight expectations must be bound to the staged desired source bytes/revision, never copied from the currently running predecessor merely because it is healthy. The implementation may derive deterministic expected tool/schema/permission/lifecycle identity from the exact staged desired source using a manager-owned, fixed, non-networked derivation seam, or equivalently prove the returned live identity directly against deterministic desired-source truth. No caller-supplied expected hashes and no auto-follow-main selector.

For the currently authorized desired source, tests/evidence must prove the derived identities equal:

- tool manifest: `24773501ac038027a69a967b1db135648d6af4d997ba417ebb9b7df4c34709d5`
- full schema: `d9ae8978040f83d476ded53abc4f3dea58216d18f0bd1e7272c3efd8c5eecee7`
- permission policy: `45910e1e37069abf3d5b01f15196548da094e2fc6b71cf8a6136e8cdf9fd71cf`
- lifecycle: `nexus.lifecycle.gateway.v2`
- tool count: 29

The exact full tool set is authoritative through its manifest/schema hashes; do not add `gateway-rebind` to the Nexus Gateway tool list.

### J5 — retain crash/lost-ack/reconcile authority

Do not redesign `_gateway_recover_with_adapters(...)`. It remains the sole R1 transition/one-effect/replay authority. Production adapter wiring must preserve:

`REQUESTED -> PREFLIGHTED -> TARGET_READY -> ROLLBACK_READY -> EFFECT_STARTED -> SERVICE_OBSERVED -> IDENTITY_VERIFIED -> CLIENT_BOUND -> VERIFIED`

and existing `UNCERTAIN_EFFECT`, `ROLLED_BACK`, `BLOCKED`, owner-liveness, idempotency-fence, evidence replay, and exactly-one-effect semantics.

A timeout/lost acknowledgement after effect must re-observe/reconcile the same request/fence; it must not call the effect again.

## Required negative controls

Tests must fail closed for at least:

1. public `gateway-recover` attempting any live effect;
2. caller-selected root/label/plist/endpoint/command/environment;
3. literal token or token placeholder appearing in the recovery plist;
4. desired/predecessor root substitution;
5. wrong desired HEAD/tree or dirty staged deployment;
6. wrong fixed plist bytes/hash;
7. wrong/missing PID, listener, or service label;
8. wrong or unchanged server instance after an applied reload;
9. health/initialize disagreement;
10. tool-list manifest/schema recomputation mismatch;
11. wrong desired permission/lifecycle identity;
12. synthetic recovery manifest/schema/permission hashes being accepted as live Gateway identity;
13. desired bootstrap failure without exact predecessor-only restoration attempt;
14. any DevSpace/unrelated launchctl label call;
15. replay from `EFFECT_STARTED` / `UNCERTAIN_EFFECT` causing a second effect.

No existing test may be skipped, xfailed, renamed to avoid execution, or weakened.

## Verification

Run on the exact Candidate:

```sh
python -m pytest -q tests/ops/test_mcp_gateway_durable.py -k 'r1 or recover or recovery'
python -m pytest -q tests/ops/test_mcp_gateway_durable.py
python -m py_compile scripts/ops/mcp_gateway_durable.py tests/ops/test_mcp_gateway_durable.py
git diff --check
git diff --name-only
git diff --diff-filter=D --name-only
```

If bare `python` is unavailable, prepend the repository's already-verified venv directory to `PATH` and execute the exact commands unchanged. Do not install packages or alter project/toolchain files merely to make the verifier run.

Independent review must bind exact base/head/tree/Card hash and challenge generic process/shell authority, public recovery effect widening, synthetic postflight, token leakage/placeholder launch, wrong-source identity acceptance, duplicate effect after lost acknowledgement, and false-green fake adapters.

## Exit and residual boundary

PASS means only `NEXUS_GATEWAY_R1_LIVE_HOST_ADAPTER_SOURCE_CANDIDATE_ONLY`.

After independent acceptance and merge, the coordinator must re-issue the recovery authority receipt because `final_manager_sha256` changes. Host materialization/manager installation and the actual Gateway effect remain separate evidence/authority stages. The current DevSpace 7677 surface still lacks the frozen typed `nexus.gateway_rebind.reload.v1` action; this Card does not modify DevSpace or bypass that gap with generic shell.

`AUTO_CHAIN=false` for the worker. Controller continuation across ordinary source acceptance/re-issuance does not grant DevSpace mutation or host effect beyond the Owner's exact existing Gateway-only authorization.
