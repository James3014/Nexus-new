# TASK-526-D-HOST-CARD-SHA-REBIND — Bind the contract to the actual Host Card

```yaml
task_id: TASK-526-D-HOST-CARD-SHA-REBIND
issue: 526
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
claim_mode: MANUAL_DISPATCH
base_main: 7c2e79709ec74d0844f585360b940aa0ec84489d
base_tree: 1705cedf9559c3bbdc25062209da9bbbdac009ae
work_branch: codex/issue-526-host-card-sha-rebind
corrected_host_card_sha256: f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514
stale_contract_host_card_sha256: fcd22da4ef92b7cde004523fe900c06bc1b9e67715049c95383c581e640f631f
claim_ceiling: NEXUS_GATEWAY_HOST_CARD_SHA_BINDING_SOURCE_CANDIDATE_ONLY
```

## Problem and authority

PR #538 merged the receipt-bundle contract, but the production constant
`HOST_CARD_SHA256` still contains the pre-amendment Host Card hash
`fcd22d...f631f`. The exact Host Card bytes on current GitHub `main` hash to
`f4c581...5f514`, and the merged C Card metadata also binds that value.

Issuing with the stale value would authorize against the wrong Card; issuing
with the actual value would be rejected by the contract. This Card authorizes
one narrow source/test correction Candidate. It authorizes no receipt issuance,
local store, artifact, plist, launchctl, Gateway, DevSpace, approval, merge,
runtime canary, release, or production effect.

## Exact worker mutation scope

Modify only:

- `nexus/contracts/gateway_deployment.py`
- `tests/contracts/test_gateway_deployment_contract.py`

Create/delete none. Do not modify the Host Card, C Card, INDEX, manager,
operations tests, Gateway transport, DevSpace, Planner/route/Workforce policy,
runtime/generated state, or unrelated formatting.

The coordinator-created Card/INDEX commit is authority setup and is not worker
implementation scope.

## Required correction

1. Change only the frozen `HOST_CARD_SHA256` literal from
   `fcd22da4ef92b7cde004523fe900c06bc1b9e67715049c95383c581e640f631f`
   to
   `f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514`.
2. Add a regression that computes SHA-256 of the tracked Host Card at
   `HOST_CARD_PATH` and proves it equals the frozen constant and the exact
   literal above.
3. Add or extend a pure negative control proving a hash-valid bundle/child
   carrying the stale `fcd22d...f631f` value rejects before selection or any
   effect seam.
4. Preserve all bundle order, uniqueness, hashing, revocation, freshness,
   selected-child equality, and manager behavior.

## Acceptance

- Exact Host Card blob SHA-256 and `HOST_CARD_SHA256` both equal
  `f4c581...5f514`.
- The stale `fcd22d...f631f` value rejects even when affected receipt and
  bundle hashes are recomputed.
- Valid `f4c581...5f514` fixtures pass.
- No product/manager/Host Card/INDEX drift appears in the worker commit.
- No deleted paths.

## Verification

```bash
uv run pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
uv run ruff check nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
uv run ruff format --check --preview nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
python3 -m py_compile nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
git diff --check
```

Independent review must bind exact base/head/tree/Card hashes and verify the
stale value fails with recomputed child and bundle hashes rather than a
false-green outer-hash failure.

## Dependencies and exit

- The Git-tracked three-child authority bundle remains blocked until this
  correction Candidate is independently accepted, merged, and read back.
- Host activation remains blocked until the later coordinator-only issuance PR
  and all Host Card physical gates pass.
- `PASS` means only
  `NEXUS_GATEWAY_HOST_CARD_SHA_BINDING_SOURCE_CANDIDATE_ONLY`.
- `AUTO_CHAIN=false`; worker stops after one source/test Candidate.
