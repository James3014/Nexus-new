# Campaign Index: github-issue-1032-b3-mimo-route-20260920

artifact_authority: current
owner: James Chen
status: active, governed and sequential
execution_lane: GOVERNED
AUTO_CHAIN: false

## Source import

- Issue #1032 settled source contract: comment `5742546265`
- R2 prerequisite terminal: #1025 comment `5748167161`
- bootstrap tracking authority: #1032 comment `5748198059`
- base main: `ed146f372842c9a3273c0e241a748fac7ef73735`
- base tree: `a4efa00d88e663e15c07a0e1cab06ef234ded188`

## Objective

Land the smallest canonical Planner/Workforce route delta needed for the #982 B3 governed OpenCode MiMo enforcement witness, preserving existing authority owners and normal routing.

## Coverage

| Requirement | Card | Status |
|---|---|---|
| Verified B3 campaign projects candidate-generation-only behavior | `00-b3-mimo-route.md` | ACTIVE |
| B3 route resolves to existing `opencode_mimo_free` | `00-b3-mimo-route.md` | ACTIVE |
| Normal routing unchanged | `00-b3-mimo-route.md` | ACTIVE |
| Unverified/text-only/caller override cannot mint route | `00-b3-mimo-route.md` | ACTIVE |
| Candidate independently accepted and governed-integrated | `00-b3-mimo-route.md` | ACTIVE |

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `issue-1032-b3-mimo-route-20260920` | `00-b3-mimo-route.md` | ACTIVE | #1025 R2 terminal physical convergence |

## Dependency frontier

Current frontier:

`issue-1032-b3-mimo-route-20260920`

Already satisfied:
- #1025 closed completed;
- loaded Gateway is R1-capable and physically verified;
- current collaboration source and exact seams rebound;
- no overlapping open PR observed on the four frozen implementation paths.

Downstream, not authority supplied by this Card:
- bind Gateway/runtime to accepted #1032 merged source;
- compile/create #982 B3 governed grant from real Planner/Workforce envelope;
- positive OpenCode NEXUS_GOVERNED read-only canary;
- same-grant widening/tamper negative;
- Wave 3 receipt.

## Campaign claim ceiling

Before source acceptance/integration:
`B3_MIMO_ROUTE_GOVERNED_CANDIDATE_ONLY`

After accepted/integrated source:
`B3_MIMO_ROUTE_SOURCE_VERIFIED`

Runtime/provider enforcement remains owned by #982 B3.

`AUTO_CHAIN=false`.
