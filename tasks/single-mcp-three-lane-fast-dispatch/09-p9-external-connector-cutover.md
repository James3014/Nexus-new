# Task Card P9: External Connector Identity Cutover

## Identity

- task_id: `single-mcp-three-lane-p9-external-connector-cutover`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: HARD_BLOCK
- owner: James Chen
- objective: Replace the stale external DevSpace MCP surface with the canonical Nexus gateway and prove fresh artifact identity across two clean starts before claiming one GPT-visible MCP registration.
- read_only: true
- audit_only: true
- commit_required: false
- candidate_required: false
- worker_may_commit: false
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Allowed Files

- `tasks/single-mcp-three-lane-fast-dispatch/INDEX.md`
- `tasks/single-mcp-three-lane-fast-dispatch/09-p9-external-connector-cutover.md`

## Required Behavior

1. Verify the external artifact source commit, package version, runtime identity, tool manifest, and public `/mcp` endpoint.
2. Install or restart only through the external package's formal release/operator surface after explicit owner authorization.
3. Perform two clean starts and prove the same `nexus-mcp-gateway` identity, manifest revision, and source/artifact hashes.
4. Verify one GPT-visible MCP registration points to that artifact and no second Nexus lifecycle MCP remains registered.

## Block Evidence

- The campaign explicitly forbids mutation of `/Users/jameschen/Workspace/nexus-devspace-mcp` and public connector cutover before identity/security/two-start gates.
- Current external source is clean at `nexus/mcp-tools-v1` commit `d18bd7ef`.
- Global installed package is `@nexus-local/devspace@1.0.1-nexus.2`; it is not the canonical gateway artifact.
- `/Users/jameschen/.codex/config.toml` contains no Nexus MCP registration; only unrelated MCP entries were found.

## Unblock Decision

Owner must authorize a separate external-artifact cutover task with exact allowed
external files, install/restart commands, connector identity, and rollback
surface. Until then the canonical gateway implementation is complete through
P8, but the campaign completion gate remains open.
