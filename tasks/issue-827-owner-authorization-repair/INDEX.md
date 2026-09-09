# Campaign Index: issue-827-owner-authorization-repair

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Owner authorized repair in this task: repair PR 829 Candidate 2a49606cd503844643ddca5e8974f12d6cbbe0e3 for Issue 827. Luna implements; primary coordinator independently verifies. Require independently rooted exact Owner authorization, reject self-issued and in-memory-only authorization, preserve one-shot replay and readback-only lost ACK, internal collaboration and DevSpace UNKNOWN_BLOCKED. Reuse existing signing/trust primitives where applicable; no live third-party publication. Produce regression RED then GREEN, scoped immutable commit and independent acceptance; no merge authority is granted by this card.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `owner-oracle-repair` | `00-owner-oracle-repair.md` | ACTIVE | Owner confirmation |
