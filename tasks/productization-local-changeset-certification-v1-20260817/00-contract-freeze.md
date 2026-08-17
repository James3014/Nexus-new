---
schema: nexus.task_card.v1
task_id: productization-local-changeset-certification-v1-20260817
card_id: 00-contract-freeze
status: COMPLETE
frontier_status: TERMINAL_RECONCILIATION
terminal_marker: LOCAL_CHANGESET_CERTIFICATION_CONTRACT_FROZEN
claim_ceiling: LOCAL_CHANGESET_CERTIFICATION_CONTRACT_ONLY
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
materialised local ChangeSet.  The contract exposes exactly three semantic
outcomes: `CERTIFIED`, `REJECTED`, and `BLOCKED`.

Certification binds a ChangeSet identity (`change_set_id`, source revision,
target revision, and content-addressed diff hash) to content-addressed,
explicit evidence references.  Canonical JSON serialization and a SHA-256
canonical hash make the wire representation reproducible.  Missing material
blocks; malformed, duplicate, contradictory, or substituted identities reject.

## Acceptance

- `nexus.changeset_certification.v1` is the only schema emitted.
- A complete internally consistent payload is `CERTIFIED`.
- Missing evidence is `BLOCKED`; malformed or hostile substitutions are
  `REJECTED`.
- Canonical serialization is key-order independent and rejects ambiguous
  object stringification.
- The module has no provider, adapter, runtime, filesystem, shell, GitHub, or
  patch/application authority.
- `AUTO_CHAIN=false`; downstream runtime integration is a separate future task.

## Non-goals

No ChangeSet discovery, diff computation, file read/write, patch application,
provider/model invocation, repository/GitHub operation, approval, merge,
release, production, or public-readiness claim is made by this contract.
