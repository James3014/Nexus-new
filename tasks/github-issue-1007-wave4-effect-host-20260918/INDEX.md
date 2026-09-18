# Issue #1007 Wave 4 — effect authority host wiring and code-integrity evidence

artifact_authority: current
status: ACTIVE
owner: James Chen
execution_lane: GOVERNED
AUTO_CHAIN: false

## Current frontier

- Durable owner: `James3014/Nexus-new#1007`
- Source base: `17c80122d2ad850d875b77e18a80534212b9b806`
- One tracked Task Card governs the bounded Wave 4A + 4B source change.
- Wave 4A: runtime dependency rebind, managed host identity plumbing, fail-closed worker boundary, Open SWE exposure receipt transport/readback.
- Wave 4B: scoped `code_integrity_v1` evidence lane plus explicit legacy CapabilityGate non-authority marker.

## Dependency frontier

1. Merge this authority artifact before production-source mutation Candidate work.
2. Rebind source base after the authority merge; source Candidate must descend from that merged authority revision.
3. Wave 4A and Wave 4B are both within the Owner's present Wave 4 request; no authority extends beyond the exact Task Card.
4. Independent acceptance is required before governed source merge.
5. Source merge is not runtime/release/production activation.

## Next gate

Merge this authority-only change, rebind Nexus-new main, then create the Wave 4 source Candidate under the exact tracked Task Card.
