# TASK-TG8-PROTOCOL-CANDIDATES — Non-promoting RC/Stable evidence subjects

- **Ready Issue:** `#802`
- **Parent:** `#772` / PR `#801`
- **Exact starting HEAD:** `d005c6e013d9f2a5315092b3aaf375b9ae322d7c`
- **Task type:** `EVIDENCE_MATERIALIZATION`
- **Status:** `ACTIVE`
- **Auto-chain:** `false`
- **Claim ceiling:** `TG8_PROTOCOL_CANDIDATE_BYTES_MATERIALIZED_FOR_EVIDENCE_ONLY`

## Goal
Produce two immutable evidence-only descendants of the exact TG8 gate Candidate: RC with public protocol `1.0.0-rc.1`, then Stable with public protocol `1.0.0`. Stable must descend directly from the accepted RC evidence subject. Neither is a public promotion.

## Allowed worker mutation
- `product/protocol/__init__.py`

Coordinator-created files under `tasks/tg8-protocol-candidate-20260905/` are governance bindings, not worker mutation scope.

## Required invariants
- `IMPLEMENTATION_SCHEMA` and every non-public-version protocol/schema constant remain byte-identical to the exact starting subject.
- Package/distribution version is not changed or conflated with public protocol version.
- No release/tag/publish/deploy/production/public promotion or protected-main mutation.
- No synthetic matrix/receipt may substitute for later TG8 physical observations.

## Candidate generations
1. **RC:** replace only `PUBLIC_PROTOCOL_VERSION = "0.1.0-experimental"` with `PUBLIC_PROTOCOL_VERSION = "1.0.0-rc.1"`; commit and bind commit/tree/blob.
2. **Stable:** from exact RC commit, replace only that line with `PUBLIC_PROTOCOL_VERSION = "1.0.0"`; commit and bind commit/tree/blob.

## Verification
For each generation:
- exact diff shows only the authorized public-version line in Product source;
- `python -m py_compile product/protocol/__init__.py`;
- relevant protocol/runtime/client/product tests pass on the exact subject;
- build/install sanity must succeed before TG8 consumes the subject;
- `git diff --check`;
- current source/tree/blob identities are recorded.

## Exit
PASS only when RC and Stable immutable commit/tree/blob identities exist and are usable by #772 physical compatibility/conformance/upgrade/rollback execution. This Task does not itself satisfy `PROTOCOL_RC_EVIDENCE_READY` or `PROTOCOL_STABLE_EVIDENCE_READY`.
