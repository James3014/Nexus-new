---
schema: nexus.task_card.v1
task_id: productization-local-changeset-certification-v1-20260817
card_id: 00-contract-freeze
status: ACTIVE
frontier_status: CANDIDATE_PENDING_INDEPENDENT_ACCEPTANCE
terminal_marker: null
claim_ceiling: LOCAL_CHANGESET_CERTIFICATION_V1_CONTRACT_CANDIDATE_ONLY
AUTO_CHAIN: false
allowed_files:
  - nexus/contracts/changeset_certification.py
  - tests/contracts/test_changeset_certification.py
  - tasks/productization-local-changeset-certification-v1-20260817/INDEX.md
  - tasks/productization-local-changeset-certification-v1-20260817/00-contract-freeze.md
---

# Local ChangeSet Certification v1

## Scope

Freeze a deterministic, provider-neutral certification contract for a fully
materialised local ChangeSet. The contract exposes exactly three semantic
outcomes: `CERTIFIED`, `REJECTED`, and `BLOCKED`.

Certification binds task/attempt, repository/source, base commit/tree, diff,
allowed scope/deletion policy, optional Candidate, verifier manifest and every
artifact/status/hash to canonical payload and manifest hashes. Missing material
blocks; malformed, duplicate, contradictory, stale, cross-bound, or substituted
claims reject.

## Acceptance

- `nexus.changeset_certification.v1` with version `1` is the only schema emitted.
- A complete internally consistent envelope is `CERTIFIED`; failed verifiers
  and hostile substitutions are `REJECTED`; missing material is `BLOCKED`.
- Canonical serialization is key-order independent, finite, and rejects
  ambiguous object stringification; set-like collections normalize deterministically.
- Unknown schema/status/reason and cross-task/attempt/source/tree/Candidate,
  manifest, artifact, or hash substitutions never certify.
- The module has no provider, adapter, runtime, filesystem, shell, GitHub, or
  patch/application authority.
- `AUTO_CHAIN=false`; independent acceptance remains pending and downstream
  runtime integration is a separate future task.

## Non-goals

No ChangeSet discovery, diff computation, file read/write, patch application,
provider/model invocation, repository/GitHub operation, approval, merge,
release, production, or public-readiness claim is made by this contract.
