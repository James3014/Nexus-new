# Campaign Index: Single MCP Three-Lane Fast Dispatch

artifact_authority: current
owner: James Chen
status: active
campaign_id: single-mcp-three-lane-fast-dispatch
source_specification: owner-authorized single-MCP gateway and three-lane implementation plan from 2026-08-01
AUTO_CHAIN: false

## Authority

- Daily source checkout: `/Users/jameschen/Workspace/nexus`
- Daily branch: `nexus/integration/main`
- Canonical lifecycle state: `/Users/jameschen/Workspace/nexus-self-hosted-state`
- Isolated Target root: `/Users/jameschen/Workspace/nexus-runtime-targets`
- Retired worktree root: `/Users/jameschen/Workspace/nexus-worktrees`

## Objective

Expose one GPT-visible Nexus MCP Gateway that routes work through
`DIRECT_CANONICAL`, `ASSISTED_CANONICAL`, or `ISOLATED_TARGET`. Ordinary small
work must remain in the canonical checkout or use a read-only bounded model
assist; only delegated, parallel, dirty, high-risk, or tool-using work may
allocate a governed Target. Every response must end in a terminal receipt or
one explicit executable next action.

## Ordered Cards

1. `00-p0-authority.md` - `single-mcp-three-lane-p0-authority`
2. `01-p1-gateway-foundation.md` - `single-mcp-three-lane-p1-gateway-foundation`
3. `02-p2-dispatch-router.md` - `single-mcp-three-lane-p2-dispatch-router`
4. `03-p3-assisted-canonical.md` - `single-mcp-three-lane-p3-assisted-canonical`
5. `04-p4-direct-completion.md` - `single-mcp-three-lane-p4-direct-completion`
6. `05-p5-isolated-closure.md` - `single-mcp-three-lane-p5-isolated-closure`
7. `06-p6-runtime-cutover.md` - `single-mcp-three-lane-p6-runtime-cutover`
8. `07-p7-telemetry.md` - `single-mcp-three-lane-p7-telemetry`
9. `08-p8-soak-gate.md` - `single-mcp-three-lane-p8-soak-gate`
10. `09-p9-external-connector-cutover.md` - `single-mcp-three-lane-p9-external-connector-cutover`
11. `10-p10-compatibility-adapter-cutover.md` - `single-mcp-three-lane-p10-compatibility-adapter-cutover`
12. `11-p11-gateway-contract-hardening.md` - `single-mcp-three-lane-p11-gateway-contract-hardening`
13. `12-p12-finish-contract-alias.md` - `single-mcp-three-lane-p12-finish-contract-alias`

## Current Frontier

`single-mcp-three-lane-p12-finish-contract-alias`

## Completed Cards

- `single-mcp-three-lane-p0-authority`: committed `d5a4547d2`; Direct receipt `cb5c9c358c3062777e69c1a92e54719a5b60ba02f635cfaf5e6a5a3e450e11f5`
- `single-mcp-three-lane-p1-authority`: card committed `1cd87459f`; runtime committed `77ea9c314`; Direct receipt `896357ffe63f7f6106849beeea04254c7bae2706aab13681c6bcca0846234b6d`
- `single-mcp-three-lane-p2-dispatch-router`: runtime/scope committed `940a6796d`; Direct receipt `f3550ff6ce91b8ff3a5361343612344e1b3b2907643d3dd610f1bfbb934235c1`
- `single-mcp-three-lane-p3-assisted-canonical`: runtime committed `e556d507a`; Direct receipt `96685865b699117ab7e8825d3a721336006dcb964e34c171bd4dd3697b314e7a`
- `single-mcp-three-lane-p4-direct-completion`: runtime committed `123e63994`; Direct receipt `8c4e99504774485d0424cc2712207028b8a148c2024b4fba713cab517dc14f52`
- `single-mcp-three-lane-p5-isolated-closure`: runtime committed `52db1a004`; Direct receipt `a19a06dbd53c5b4259413f762a15c5e44f053d3a7a59972baf5256aacc4ba83e`
- `single-mcp-three-lane-p6-runtime-cutover`: runtime committed `595b83c95`; Direct receipt `a63177872d989fe16e792ebebbe8a5fc81e01edb58da00e48cfc84bfa9841996`
- `single-mcp-three-lane-p7-telemetry`: runtime committed `b05c3730c`; Direct receipt `31fc2111469a136275990d2e7bfe8e5782675f5108e0cf4cb5e80be7c144b057`
- `single-mcp-three-lane-p8-soak-gate`: runtime committed `cb44a1177`; Direct receipt `ec89709f87b7685f8481ae9a15ea1ce75c290804abbeba92de4346dabbbb36b7`
- `single-mcp-three-lane-p10-compatibility-adapter-cutover`: runtime committed `4c8604928`; Direct receipt `3ef82182e7dd13dec3470594f2c08d1bbbe863c7a26ddf1519f8455d7209ef7c`
- `single-mcp-three-lane-p11-gateway-contract-hardening`: runtime committed `727c8b592`; Direct receipt `ffa75a97df0bf08b02226c92ef94cd42de1b309ece98ace7a8743dd83fed011a`

## Dependencies

P1 depends on P0. P2 depends on P1. P3 and P4 depend on P2. P5 depends on
the existing lifecycle closure and P1. P6 depends on P1-P5. P7 depends on
P2-P6. P8 depends on every implementation card and fresh runtime inventory.
P9 requires an owner-authorized external artifact refresh and connector
registration; it is not executable under the current campaign forbidden scope.
P10 is a corrective compatibility-adapter card: it closes the stale P0 wrapper
behavior without mutating the external DevSpace repository.
P11 hardens the canonical gateway receipt contract and does not authorize any
external provider transmission or connector mutation.
P12 closes the public Direct finish contract using the gateway's `base_sha`
alias; it is canonical-only and does not alter external registration.

## Global Forbidden Scope

- No direct lifecycle JSON edits.
- No mutation of `/Users/jameschen/Workspace/nexus-devspace-mcp` in this campaign.
- No public connector cutover before identity, security, and two-start gates pass.
- No worker approval, integration, push, protected history rewrite, or branch/ref deletion.
- No use or recreation of `nexus-worktrees`.
- No removal of salvage evidence.

## Completion Gate

The campaign is complete only when one GPT-visible MCP registration exposes the
unified gateway, 20 bounded assist tasks and 10 Direct tasks create no Target,
10 isolated tasks leave no Target after Candidate formation, runtime identity
matches the exact source/artifact hashes, actionable tasks are zero after
owner dispositions, and the canonical checkout remains clean with one
registered worktree.
