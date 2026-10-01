# TASK-526-C-RECEIPT-BUNDLE — Pre-authorize the complete host effect sequence

```yaml
task_id: TASK-526-C-RECEIPT-BUNDLE
issue: 526
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
claim_mode: MANUAL_DISPATCH
base_main: a5f6de006637c61e8073cbdc4dd6d43e96307787
base_tree: 57184a06f0bae4d86fca101f236e485e4c8b121d
work_branch: codex/issue-526-host-receipt-bundle
host_card_sha256: f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514
claim_ceiling: NEXUS_GATEWAY_HOST_RECEIPT_BUNDLE_CONTRACT_SOURCE_CANDIDATE_ONLY
```

## Problem and authority

The merged host-authority contract correctly makes every receipt exact to one
operation/effect/request/fence and rejects cross-operation reuse. The fixed
Git-tracked authority path, however, currently parses one receipt. The legal
activation sequence needs a separate stable-artifact install authority, reload
authority, and rollback authority already available before a reload failure.
Replacing GitHub main between effects is unsafe and cannot guarantee rollback.

This Card authorizes one source/test Candidate to define an immutable bundle of
independent operation receipts. It authorizes no Git-tracked bundle issuance,
local store, artifact, plist, launchctl, Gateway, DevSpace, approval, merge,
release, or runtime/public effect.

## Exact mutation scope

Modify only these four existing files; create/delete none:

- `nexus/contracts/gateway_deployment.py`
- `scripts/ops/mcp_gateway_durable.py`
- `tests/contracts/test_gateway_deployment_contract.py`
- `tests/ops/test_mcp_gateway_durable.py`

Do not edit Cards/INDEX during implementation, Gateway HTTP/stdio, DevSpace,
Planner/route/Workforce policy, runtime/generated state, or unrelated paths.

## Required pure contract

1. Add strict `HostEffectAuthorityBundle` with schema
   `nexus.gateway.host_effect_authority_bundle.v1`, exact bundle version `1`,
   bundle ID/hash, repository, host Card ID/path/SHA, authority-contract source
   merge/tree/manager/acceptance/current-main identities, validity/revocation
   envelope, and an immutable tuple of strict `HostEffectAuthorityReceipt`.
   Bundle revocation fields are `revocation_state`, `revoked_at`, and
   `revocation_reason` and are covered by the bundle hash.
2. The canonical bundle contains exactly one each of:
   - `install-artifact / INSTALL_ARTIFACT`;
   - `reload / GATEWAY_RELOAD`;
   - `rollback / GATEWAY_ROLLBACK`.
   No missing, extra, duplicate, status, preflight, alias, or unknown operation
   is accepted. The reload request's internal preflight uses the same receipt.
3. Each child keeps its own exact receipt hash, request ID, idempotency fence,
   operation/effect, profile/service/Card/source/freshness/revocation bindings.
   Receipt IDs, request IDs, and fences are globally unique inside the bundle.
4. Bundle canonical hash covers every child byte-semantic value in stable order.
   Child reordering, mutation, duplication, removal, or addition changes the
   hash and fails. Unknown fields fail.
5. A `GatewayDeploymentRequest` still carries one exact child receipt. Pure
   validation does not treat the bundle as a cross-operation grant.
6. Separate evidence parsing from effect eligibility:
   - strict bundle parsing/hash validation may represent either active
     `NOT_REVOKED` children/bundle or a revoked evidence state;
   - a revoked bundle requires `revocation_state=REVOKED`, non-empty
     `revoked_at`/`revocation_reason`, and at least one consistently revoked
     child; a revoked child uses the same exact non-null revocation fields;
   - effect selection requires bundle `NOT_REVOKED`, null bundle revocation
     fields, and every child `NOT_REVOKED` with null child revocation fields;
   - if the bundle or any child is revoked, no operation may be selected and
     all observation/effect seams remain untouched.

## Required manager enforcement

1. The fixed Git-tracked/local path remains
   `02-host-effect-authority-receipt.json`; its strict content is now the bundle.
2. Preserve fixed public origin/main, clean trusted source HEAD, `ls-remote`,
   `git show`, safe UID/modes/size/symlink/duplicate-key, and byte-equality
   controls before observation/effect.
3. Parse/validate the complete bundle, then select exactly one child whose
   receipt ID, operation/effect, request ID/fence, and full typed value equal the
   request receipt. Missing/ambiguous/non-equal selection rejects.
4. No caller selects bundle path, remote, ref, operation entry, command runner,
   or receipt mapping. Production uses fixed commands; tests inject command
   outputs only.
5. Every host entrypoint and CLI operation revalidates the latest bundle before
   its first effect. Parsing may preserve revoked evidence, but active effect
   selection rejects a revoked/expired bundle or any revoked child.
6. Ledger remains bound to the selected child; it never treats the bundle as a
   broad effect grant.

## Acceptance and negative controls

- single legacy receipt at the fixed path: reject;
- missing/extra/duplicate/reordered child, wrong bundle hash/version/schema,
  duplicate receipt/request/fence, alias operation, or cross-child substitution:
  reject before authority/host observer or effect;
- install request cannot select reload/rollback receipt and vice versa;
- bundle with valid unselected children but invalid selected child: reject;
- bundle/child stale, future, revoked, wrong actor/grant/Card/source/profile:
  reject;
- revoked bundle/child parses as evidence only when revocation fields are
  internally consistent, but selection of every operation rejects with zero
  authority/host observer and zero effect;
- Git-tracked bytes versus local bytes mismatch: reject;
- same-UID locally fabricated bundle absent from remote main: reject;
- positive tests separately execute install, reload, and rollback request
  validation against the same immutable bundle without actual host effects;
- all previous source-only, operation-ordering, fixed-status, ledger/fence,
  artifact, postflight, rollback, and legacy tests remain green.

## Verification

```bash
uv run pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
uv run ruff check nexus/contracts/gateway_deployment.py scripts/ops/mcp_gateway_durable.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
uv run ruff format --check --preview nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
python3 -m py_compile nexus/contracts/gateway_deployment.py scripts/ops/mcp_gateway_durable.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
git diff --check
```

Independent review must bind exact base/head/tree/Card hashes, challenge bundle
broadening, selection ambiguity, child uniqueness, stale/revoked behavior, and
false-green store mismatch tests.

## Dependencies and exit

- `TASK-526-HOST-1` remains BLOCKED until this Candidate is independently
  accepted/merged and a separate coordinator-only reviewed/CAS PR creates the
  exact three-child bundle on GitHub main.
- Gateway-only local canary performs zero DevSpace effects; future
  DevSpace/ChatGPT-facing work remains `SERIALIZE_AFTER:#398`.
- `PASS` means only
  `NEXUS_GATEWAY_HOST_RECEIPT_BUNDLE_CONTRACT_SOURCE_CANDIDATE_ONLY`.
- `AUTO_CHAIN=false`; worker stops after one source/test Candidate.
