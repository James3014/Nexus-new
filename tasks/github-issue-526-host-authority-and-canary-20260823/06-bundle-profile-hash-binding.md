# TASK-526-F-BUNDLE-PROFILE-HASH-BINDING

    task_id: TASK-526-F-BUNDLE-PROFILE-HASH-BINDING
    issue: 526
    repository: James3014/Nexus-new
    status: ACTIVE
    auto_chain: false
    claim_mode: MANUAL_DISPATCH
    base_main: 6e261f22144eb7721d82af57edd6530c89cfa45d
    base_tree: 8cb1dc8b8c0fbc81d8e25df0dd38655881128da9
    work_branch: codex/issue-526-bundle-profile-bind
    host_card_sha256: f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514
    claim_ceiling: NEXUS_GATEWAY_BUNDLE_PROFILE_BINDING_SOURCE_CANDIDATE_ONLY

## Problem and authority

The coordinator-only issuance Candidate contains the correct frozen current and
desired profile hashes. Independent adversarial review proved that standalone
bundle validation accepts a different valid 64-hex profile hash when the child
and outer hashes are recomputed. The later request-selection path rejects it,
but the Host Card requires the authority bundle itself to bind the frozen
profiles.

This Card authorizes one pure contract/test Candidate. It authorizes no bundle
issuance or commit, local materialization, mirror update, artifact, plist,
launchctl, Gateway, DevSpace, approval, merge, activation, rollback, release,
or production effect.

## Exact worker mutation scope

Modify only:

- nexus/contracts/gateway_deployment.py
- tests/contracts/test_gateway_deployment_contract.py

Create/delete none. Do not edit Cards/INDEX, manager, operations tests,
runtime/generated state, or unrelated formatting.

## Required correction

1. Standalone HostEffectAuthorityReceipt validation must require:
   - current_profile_hash equals canonical_hash(CURRENT_PROFILE);
   - desired_profile_hash equals canonical_hash(DESIRED_PROFILE).
2. This check applies to every child during bundle validation, before request
   selection or any manager/remote/host observation.
3. Keep existing complete-frozen-profile equality, bundle/child shared
   provenance, receipt hash, bundle hash, ordering, uniqueness, freshness, and
   revocation gates unchanged.
4. Do not add caller-selected profiles or a second profile authority.

## Acceptance

- Correct current/desired frozen hashes pass standalone receipt and bundle
  validation.
- For each profile-hash field independently, replace it with another valid
  64-hex value, recompute the child receipt hash and outer bundle hash, and
  prove standalone bundle validation rejects at the intended profile gate.
- Rejection happens before request selection, remote authority, observer, or
  host effect seams.
- Existing contract and operations suites remain green.
- Exactly two worker files, no deletions, no test rename/skip/xfail/deselection.

## Verification

    uv run pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
    uv run ruff check nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
    uv run ruff format --check --preview nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
    python3 -m py_compile nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
    git diff --check

Independent review must bind exact base/head/tree/Card hashes and confirm the
negative controls recompute both hash layers.

## Dependencies and exit

- Bundle issuance remains blocked until this Candidate is independently
  accepted, merged, and the clean authority mirror is updated to new main.
- PASS means only
  NEXUS_GATEWAY_BUNDLE_PROFILE_BINDING_SOURCE_CANDIDATE_ONLY.
- AUTO_CHAIN=false; worker stops after one two-file Candidate.
