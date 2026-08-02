# MCP 2026-07-28 Dual-Stack Transport

```yaml
campaign_id: mcp-2026-07-28-dual-stack-transport
authority: tasks/mcp-2026-07-28-dual-stack-transport/00-surface-identity-dual-stack-transport.md
owner: James Chen
status: ACTIVE
frontier: 00-surface-identity-dual-stack-transport.md
auto_chain: false
source_campaign: single-mcp-three-lane-fast-dispatch
source_card: tasks/single-mcp-three-lane-fast-dispatch/13-p13-external-gateway-cutover.md
ordered_cards:
  - 00-surface-identity-dual-stack-transport.md
completed: []
blocked: []
deferred:
  - principal_bound_workspace_handles_and_ttl
  - oauth_restart_durability_and_client_id_metadata_documents
  - end_to_end_trace_context
  - tasks_extension_projection
  - mcp_apps_modern_negotiation
```

The active card changes only the public DevSpace protocol boundary and its
surface identity. CapabilityPlanner, UnifiedRuntime, existing task state,
Candidate authority, and the canonical Gateway tool manifest remain the sole
internal authorities.

Downstream cards remain deferred until the dual-stack spike proves modern and
legacy compatibility without widening shell, filesystem, approval, integration,
or credential authority.
