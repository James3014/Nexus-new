# Campaign Index: legacy-mcp-seam-rationalization-20260809

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Make `nexus_worker_candidate` the single obvious remote implementation ingress
by classifying and narrowing legacy/dead MCP mutation seams without creating a
new router, provider selector, or lifecycle.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `LEGACY-MCP-SEAM-RATIONALIZATION-01` | `00-LEGACY-MCP-SEAM-RATIONALIZATION-01.md` | ACTIVE | P1 source integration; non-overlap with active worker-readiness Candidate |

## Governance

- UnifiedMCPGateway remains the current public transport surface.
- CapabilityPlanner/HybridRouteDecision remain route authority.
- Worker may commit one scoped Candidate only; approval, integration, reload,
  cleanup, and push remain primary/Owner actions.
- `AUTO_CHAIN=false`.
