# TASK-526-I — TASK-002 recovery activation lineage rebind

```yaml
task_id: TASK-526-I-TASK002-RECOVERY-ACTIVATION-REBIND
issue: 526
repository: James3014/Nexus-new
status: READY_FOR_IMPLEMENTATION
execution_realm: EXTERNAL_BOOTSTRAP_SOURCE_ONLY
auto_chain: false
claim_mode: MANUAL_DISPATCH
claim_ceiling: NEXUS_GATEWAY_TASK002_ACTIVATION_SOURCE_CANDIDATE_ONLY
owner_authorization_comment_id: 5418927784
owner_authorization_comment_sha256: 61ebd493c8a405213043382dc1bb0d225185c5528126573311de2cba9cff4eb9
```

## Goal

Make the current Owner-authorized TASK-002 Gateway recovery target machine-verifiable without widening the historical Issue #526 host authority or making public Gateway recovery effectful.

The current Owner authorization is durably projected in Issue #526 comment `5418927784`. It authorizes exactly:

- desired Gateway commit/tree: `b2a9cca573580d2edbd5531bb9e4bf92479e0e3a` / `747d9dcecd47dff3d063e7948496d8adb33f50bc`;
- exact predecessor commit/tree: `3d28fa7b65df30e207e53de7caadf93a2b7a8fc0` / `5e6476b2b12211e7cdcfe9294942b633ffbcef59`;
- only `com.nexus.mcp.gateway.direct` host recovery/rebind;
- no DevSpace, other service, unrelated worktree, Planner/route/Workforce, release, production, or auto-follow-main effect;
- rollback reconstruction before the first process effect and authenticated identity proof afterward;
- resume TASK-002 only after verified Gateway recovery; no TASK-003 auto-chain.

The historical activation `OWNER_ISSUE526_CONTINUE_20260823` and its old receipt/bundle remain historical evidence. They must not be relabeled, rewritten, or accepted as authority for the new exact TASK-002 desired/predecessor pair.

## Authority and non-goals

This Card authorizes one source/test Candidate only. It authorizes no receipt issuance, local authority-store materialization, source-bundle/worktree staging, plist/launchctl write, Gateway or DevSpace process effect, Candidate approval, merge, runtime activation, release, or production/public claim.

Preserve these R1 invariants:

- public `gateway-recover` remains effect-free/non-injectable;
- `_gateway_recover_with_adapters` remains the internal separately-authorized host effect/reconcile engine;
- one fixed Gateway label/plist/endpoint and no generic shell/process/root selector;
- old valid receipts remain parseable/valid for their historical semantics except that the old activation must fail closed if substituted onto the new TASK-002 target pair;
- the new activation cannot authorize any other desired/predecessor commit/tree;
- standing grant, R1 Card identity, accepted source lineage, revocation, freshness, manifest derivation, request/fence, and source-set checks remain unchanged.

## Exact source mutation scope

Modify only:

- `nexus/contracts/gateway_deployment.py`
- `tests/contracts/test_gateway_deployment_contract.py`

Create/delete none. Do not modify `scripts/ops/mcp_gateway_durable.py`, Gateway HTTP/stdio, DevSpace, Task #129 source, Planner/route/Workforce, runtime/generated state, historical receipt/bundle files, or any LaunchAgent/local host file.

## Required behavior

Introduce the smallest versioned/allowlisted activation-lineage validation that satisfies all of these:

1. Historical activation tuple remains accepted for existing historical/generic R1 receipt cases.
2. Historical activation is rejected after full receipt rehash if it is substituted onto the exact new TASK-002 desired/predecessor identity (including commit/tree binding).
3. New activation identity is explicit and binds Issue #526 comment `5418927784` plus its SHA-256 above.
4. New activation validates only when desired commit/tree and predecessor commit/tree exactly equal the Owner-authorized values above.
5. Any new-activation target/tree substitution, mixed historical/new activation fields, unknown activation, or fully rehashed tamper fails closed.
6. Receipt canonical hash, source-set, derived manifests, revocation/freshness, fixed service and request/fence validation remain unchanged.
7. Do not add a second authority store, receipt type, scheduler, Router, Planner, worker selector, process manager, or public host-effect action.

Prefer a small dedicated activation validator/helper over broad special-casing in unrelated source-set or manifest logic.

## Required verification

Run exactly these repository checks from a clean isolated Candidate worktree:

```sh
python -m pytest -q tests/contracts/test_gateway_deployment_contract.py -k 'recovery_authority or activation'
python -m pytest -q tests/contracts/test_gateway_deployment_contract.py
python -m pytest -q tests/ops/test_mcp_gateway_durable.py -k 'recover or recovery'
python -m py_compile nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
git diff --check
git diff --name-only
```

The final name-only set must contain exactly the two allowed source/test paths and no deletion. Independent review must challenge old-activation reuse, new-activation target reuse, partial mixed lineage, full-rehash tampering, public recovery effect widening, and test weakening.

## Exit

PASS means only `NEXUS_GATEWAY_TASK002_ACTIVATION_SOURCE_CANDIDATE_ONLY`.

After independent source acceptance and merge, the coordinator may separately issue a fresh R1 recovery authority receipt using the new activation and the exact authorized desired/predecessor pair. Receipt issuance and host recovery remain separate gates.

`AUTO_CHAIN=false`
