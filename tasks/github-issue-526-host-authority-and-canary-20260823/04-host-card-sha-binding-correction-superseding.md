# TASK-526-D-HOST-CARD-SHA-REBIND — Superseding three-file correction

```yaml
task_id: TASK-526-D-HOST-CARD-SHA-REBIND
attempt_revision: 2
issue: 526
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
claim_mode: MANUAL_DISPATCH
base_main: 7c2e79709ec74d0844f585360b940aa0ec84489d
base_tree: 1705cedf9559c3bbdc25062209da9bbbdac009ae
work_branch: codex/issue-526-host-card-sha-rebind
supersedes_card_path: tasks/github-issue-526-host-authority-and-canary-20260823/03-host-card-sha-binding-correction.md
supersedes_card_sha256: a5f0fc128e18e12a0524f49aa463b2fe4b5e3f0766f3ff1d3be41564373e07cc
corrected_host_card_sha256: f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514
stale_contract_host_card_sha256: fcd22da4ef92b7cde004523fe900c06bc1b9e67715049c95383c581e640f631f
claim_ceiling: NEXUS_GATEWAY_HOST_CARD_SHA_BINDING_SOURCE_CANDIDATE_ONLY
```

## Supersession evidence

The first bounded attempt changed the contract constant and contract tests
correctly, but the Card-required operations suite failed because
`tests/ops/test_mcp_gateway_durable.py` contains one request-fixture literal
with the same stale `fcd22d...f631f` Host Card SHA. The contract suite passed
31 tests; Ruff, py_compile, and diff checks passed. The operations suite failed
60 tests at the intended contract validator with
`host authority host_card_sha256 mismatch`.

This is a Goal-preserving source-fixture rebind. It changes no product
semantics, authority level, host target, permission, irreversible effect,
release, or production claim.

## Exact worker mutation scope

Modify only:

- `nexus/contracts/gateway_deployment.py`
- `tests/contracts/test_gateway_deployment_contract.py`
- `tests/ops/test_mcp_gateway_durable.py`

Create/delete none. In the operations test file, change only the stale
`host_card_sha256` fixture at the request builder to the already imported
`HOST_CARD_SHA256` constant. Do not reformat or otherwise rewrite that file.

Do not modify Cards/INDEX, manager, Gateway transport, DevSpace,
Planner/route/Workforce policy, runtime/generated state, or unrelated paths.
The coordinator-created Card/INDEX commits are not worker implementation scope.

## Required correction

1. Preserve the existing compliant uncommitted delta:
   - frozen `HOST_CARD_SHA256=f4c581...5f514`;
   - tracked Host Card byte-hash regression;
   - stale `fcd22d...f631f` negative control with recomputed child/bundle
     hashes.
2. Replace the one operations-test request-fixture stale literal with
   `HOST_CARD_SHA256`.
3. Do not weaken, delete, skip, xfail, rename, or deselect any verifier.
4. Preserve bundle order, uniqueness, hashing, revocation, freshness,
   selected-child equality, manager behavior, and exact test node identities.

## Acceptance

- Exact Host Card bytes and contract constant equal `f4c581...5f514`.
- Hash-valid stale `fcd22d...f631f` bundle/child rejects at Card binding.
- Operations request fixtures use the corrected constant and the complete
  contract/ops suite passes.
- Worker commit changes exactly the three authorized files, with no deletions
  and no operations-test formatting noise.

## Verification

```bash
uv run pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
uv run ruff check nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
uv run ruff format --check --preview nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
python3 -m py_compile nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
git diff --check
```

Independent review must bind exact base/head/tree/Card hashes and prove the
operations-file delta is the one fixture expression only.

## Dependencies and exit

- Git-tracked authority bundle issuance remains blocked until this correction
  Candidate is independently accepted, merged, and read back.
- Host activation remains blocked until the later coordinator-only issuance PR
  and all Host Card physical gates pass.
- `PASS` means only
  `NEXUS_GATEWAY_HOST_CARD_SHA_BINDING_SOURCE_CANDIDATE_ONLY`.
- `AUTO_CHAIN=false`; worker stops after one three-file Candidate.
