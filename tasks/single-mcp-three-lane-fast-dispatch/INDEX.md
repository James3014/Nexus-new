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

## Current Frontier

`single-mcp-three-lane-p0-authority`

## Dependencies

P1 depends on P0. P2 depends on P1. P3 and P4 depend on P2. P5 depends on
the existing lifecycle closure and P1. P6 depends on P1-P5. P7 depends on
P2-P6. P8 depends on every implementation card and fresh runtime inventory.

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
