# Campaign Index: issue-827-publication-durability-repair

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Owner explicitly reaffirmed all operations necessary to complete Issue 827 in this thread after the earlier scope rejection. Repair supported publication durability and exact prepared-operation binding defects on b1136391823b7437680aa02b8b5c5d2ca349df54. Luna implements; controller independently verifies. Fsync containing directory after atomic replace using existing donor pattern; fail closed on durable write errors before dispatch; reject prepared operation/proposal/store identity mismatch and unknown remote outcome states without blind redispatch. Preserve exact Owner signature, one-shot/replay, readback-only lost ACK, internal collaboration and DevSpace UNKNOWN_BLOCKED. No new protocol, no live third-party publication, no merge or release through this card. Require regression RED/GREEN and scoped immutable commit.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `durability-repair` | `00-durability-repair.md` | ACTIVE | Owner confirmation |
