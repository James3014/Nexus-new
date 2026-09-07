# Owner Representation Authority (External Publication) — #827

Canonical fail-closed authority boundary: **agents, workers, and models can
never publish, file, comment, fork, or otherwise publicly represent the Nexus
Owner/project in a third-party repository without an explicit, exact, one-shot
Owner grant.**

| Field | Value |
| --- | --- |
| Issue | #827 (P1 governance) |
| Contract schema | `nexus.owner_representation*.v1` |
| Contract module | `nexus/contracts/owner_representation.py` |
| Authorization seam | `nexus/orchestrator/owner_representation.py` |
| Transport inventory | `nexus/security/owner_representation_transport_inventory.py` |
| Tests | `tests/nexus/orchestrator/test_owner_representation.py` |

## Invariants (non-negotiable)

- `AUTHENTICATED != OWNER_AUTHORIZED`
- `CAN_EDIT_CODE != CAN_PUBLISH`
- `CAN_COMMIT != CAN_PUBLISH`
- `CAN_PUSH != CAN_REPRESENT_OWNER`
- `CAN_MERGE != CAN_REPRESENT_OWNER`
- `TASK_COMPLETION != CAN_REPRESENT_OWNER`
- `PUSH_DENIED != ISSUE_PUBLICATION_AUTHORIZED`
- `MODEL/WORKER OUTPUT != OWNER STATEMENT`

A worker that passes tests, owns a merge grant, or records a public claim has
earned none of the above. The single source of external-publication authority
is an owner-issued one-shot `OwnerRepresentationGrant` matching the exact
proposal. **Inference derivations** (`PUSH_DENIED`, `TASK_COMPLETION`,
`WORKER_OUTPUT`, `UNTYPED`) never substitute for a grant and are blocked with
`PUSH_DENIED_IS_NOT_PUBLICATION_AUTHORITY` /
`PUBLICATION_AUTHORITY_NON_INFERABLE`.

## Execution model

1. `ExternalPublicationProposal` binds exact destination, effect, target,
   content hash (`canonical_publication_content_hash`), purpose, actor,
   transport, operation id, and derivation.
2. Destination classification is fail-closed:
   - `OWNER_CONTROLLED_INTERNAL_COLLABORATION` — only when an explicit
     `InternalCollaborationBound` contract matches destination + effect. Repo
     ownership alone never classifies. Records a passthrough; performs no
     external write.
   - `THIRD_PARTY_OR_EXTERNAL_OWNER_REPRESENTATION` — recognized public host
     (`github.com` / `gitlab.com` / `bitbucket.org`) outside the internal
     bounds, or `PUBLIC_FORK` / `PUBLISH_BRANCH_AS_EXTERNAL_CONTRIBUTION`.
     Requires an exact grant.
   - `UNKNOWN` → BLOCK (`DESTINATION_UNKNOWN`).
3. The one-shot grant must match every bound field (destination, effect,
   target, content hash, purpose, actor, transport, operation id) or the
   decision is `BLOCKED` (`DESTINATION_MISMATCH`, `FOLLOWUP_NOT_IMPLIED`,
   `TARGET_MISMATCH`, `CONTENT_SUBSTITUTION`, `PURPOSE_SUBSTITUTION`,
   `ACTOR_MISMATCH`, `TRANSPORT_MISMATCH`, `OPERATION_MISMATCH`).
   A grant valid only for `CREATE_ISSUE` never implies `COMMENT`/`EDIT`/
   `CLOSE`/`CREATE_PR`/`FORK`.
4. The durable publisher persists `PREPARED -> DISPATCHING -> COMPLETED`
   (mirroring the proven EIA publication pattern) before any physical effect
   and refuses replay:
   - `DISPATCHING` persisted before the injected write transport runs.
   - Timeout/exception/lost-ACK after dispatch → `OUTCOME_UNKNOWN` →
     **readback-only reconciliation**, never blind redispatch.
   - One-shot consumed-grant ledger keyed by `grant_hash`; reuse across a
     different operation is `GRANT_REUSED`, completion is `REPLAY_FORBIDDEN`.
5. For internal-only automation (EIA pipelines, governed push, merge intent)
   the inventory classifies those routes `BOUNDED_INTERNAL_ONLY`; existing
   behavior is preserved and is a positive control that internal automation
   still works.

## Transport inventory

| Route | Capability surface | State |
| --- | --- | --- |
| `github_orchestration` | Merge intent / GITHUB_MERGE | BOUNDED_INTERNAL_ONLY |
| `governed_push` | REPOSITORY_PUSH grant | BOUNDED_INTERNAL_ONLY |
| `external_intelligence_service` | EIA/EI pipelines | BOUNDED_INTERNAL_ONLY |
| `repository_contract_gate` | Collaboration boundary checks | INCAPABLE_OF_EXTERNAL_PUBLICATION |
| `chatgpt_connector` | ChatGPT UI ask-before-write | OWNER_INTERACTIVE_GATED |
| `codex_cli_pat` | Codex CLI / PAT | OWNER_INTERACTIVE_GATED |
| `devspace_worker` | Arbitrary delegated shell | UNKNOWN_BLOCKED |
| `morning_report_gh_guidance` | Rendered human guidance only | INCAPABLE_OF_EXTERNAL_PUBLICATION |

UI "ask before write" (ChatGPT connector or otherwise) is **defense-in-depth
only** — it is not proof of canonical authority. Third-party writes that are
actually performed on the Owner's behalf must home their authority in a
one-shot grant through the canonical seam. `assert_no_unknown_routes()` fails
closed on any silent new publication channel, and `FORBIDDEN_PROGRAMMATIC_GITHUB_WRITE_PATTERNS`
backs this with a physical source-parity test.

## Failure-mode guarantees

- Proposal without grant on a third-party destination → BLOCK.
- Proposal derived from `PUSH_DENIED` → BLOCK (regression anchor for #827).
- Grant valid but content/purpose/actor/target/transport changed → BLOCK
  (substitution).
- Same grant reused for a different operation → BLOCK (replay).
- Dispatch, then lost ACK/timeout → `OUTCOME_UNKNOWN`; reconcile reads back
  only; a second effect is never blindly issued.
- The publisher's transports are injected; the module itself is physically
  incapable of reaching a live third-party repo.