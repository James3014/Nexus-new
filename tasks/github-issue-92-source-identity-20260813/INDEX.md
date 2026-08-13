---
artifact_authority: current
owner: James Chen
status: blocked_serialize_after_issue_29
purpose: Govern the preimplementation contract for Issue #92 physical source identity validation.
baseline: 82b904a730095494213ad1dc6c54bcb09b798a47
auto_chain: false
---

# Issue #92 — Source identity validation

- GitHub Issue: `#92`
- Current frontier: `00-source-identity-preimplementation.md`
- Frontier status: `BLOCKED_SERIALIZE_AFTER_ISSUE_29`
- Claim ceiling: `TASK_CARD_COMPILED_IMPLEMENTATION_NOT_AUTHORIZED`
- `AUTO_CHAIN=false`

## Dependency fence

Issue #29 currently owns moving same-task Local-to-Online evidence and runtime
identity surfaces, including `nexus/services/unified_runtime.py`. Issue #92 may
not begin implementation until #29 reaches a physical terminal disposition and
the coordinator re-reads fresh `main`, open PR overlap, and exact source blobs.

The card compiles the contract only. It does not authorize product or test
mutation, create a Candidate, or activate downstream Issue #49.
