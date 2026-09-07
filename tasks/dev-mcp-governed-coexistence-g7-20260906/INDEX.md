# Campaign Index: G7 Nexus-Governed Coexistence

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

G7-1 rebind: carry a fresh, verifiable, current GitHub `main`-bound `NEXUS_GOVERNED` read-only authority bundle (Task Card + execution grant + INDEX) as an isolated Candidate on a non-main branch, then STOP. Later independent gates close G7: current-main authority readback, positive governed admission, bad-grant single-variable rejection, `OWNER_DIRECT` coexistence witness, no silent fallback, and physical no-mutation reconciliation.

## Frontier

| Order | Milestone | Card | Status | Dependency |
|---:|---|---|---|---|
| 1 | `g7-1-fresh-canonical-authority-rebind-20260907` | `00-g7-nexus-governed-coexistence.md` | ACTIVE (this Candidate) | Fresh canonical base `491660f2a...` |
| 2 | `g7-2-current-main-authority-readback-20260907` | (pending) | not started | G7-1 candidate present |

## Bound authority artifacts (fresh rebind)

- Task Card SHA-256 (authoritySha256): `3118948639296773a8b60d5aca2f8db192af031184a2cf084ee5290c1934c350`
- DispatchIntent hash: `e10f08fc344823a6d77899d33d7ee215d8a580c5e614efb572be25fd66740d07`
- Execution grant: `g7-execution-grant-contract.json`
- Grant raw SHA-256: `67fae23dfc905c2a8b4a4e0ec9845c2fffa11d1b4a0bb245aca0a938a08b2d24`
- Grant semantic hash: `281e7d964d50282d3211896fbd93ae839aa8b43d7793a2f629b53dd8ebe4bd1e`
- Target DevSpace base (fresh execution-time GitHub `main`): `491660f2a95eb04e68683e1648c2f9a20744a52a`
- Target profile: `opencode-muse-high-review`
- Attempt: `g7-governed-live-attempt-20260907-01`

Authority admission PASS is separate from provider result PASS and from gate COMPLETE. This rebind mints a Candidate only; it does not launch a worker, run the bad-grant live attempt, run the OWNER_DIRECT witness, reconcile physically, or mark G7 complete.
