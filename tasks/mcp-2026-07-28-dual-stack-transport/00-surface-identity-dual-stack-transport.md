# MCP Surface Identity and 2026-07-28 Dual-Stack Transport

```yaml
task_id: mcp-surface-identity-dual-stack-transport
campaign_id: mcp-2026-07-28-dual-stack-transport
owner: James Chen
status: ACTIVE
artifact_authority: current
read_only: false
audit_only: false
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
auto_chain: false
```

## Objective

Migrate the public `/mcp` boundary in `nexus-devspace-mcp` to an explicitly
opted-in MCP `2026-07-28` modern handler with a legacy compatibility route,
without changing Nexus routing, task, Candidate, approval, or runtime authority.
Resolve the live surface mismatch so public gateway mode reports and exposes the
dynamic canonical Gateway manifest, while raw 16-tool DevSpace remains an
explicit local maintenance profile rather than the Owner public default.

## Verified baseline

```yaml
verified_at: 2026-08-02
canonical_nexus:
  branch: nexus/integration/main
  head: d5fa9ca1a4efb61732418927b558ae489816c927
  gateway_protocol_version: 2024-11-05
external_source:
  root: /Users/jameschen/Workspace/nexus-devspace-mcp
  branch: nexus/mcp-tools-v1
  head: 2d1efff955a9013dfb016deca775f88cf8cdd605
  sdk: "@modelcontextprotocol/sdk ^1.29.0"
  registry_baseline:
    legacy_sdk_current: "@modelcontextprotocol/sdk 1.30.0"
    modern_server: "@modelcontextprotocol/server 2.0.0"
    modern_node: "@modelcontextprotocol/node 2.0.0"
  dirty_baseline:
    - generated/build-identity.json
    - generated/artifact-sha256.txt
    - nexus-local-devspace-1.0.1-nexus.3.tgz
installed_runtime:
  package: "@nexus-local/devspace@1.0.1-nexus.3"
  source_commit: 2d1efff955a9013dfb016deca775f88cf8cdd605
  health:
    name: devspace
    proxy_mode: false
    gateway_url: null
  declared_default_surface: nexus-mcp-16-v1
  declared_default_tool_count: 16
  embedded_gateway_tool_count: 24
observed_defects:
  - public runtime is raw DevSpace rather than canonical Gateway proxy mode
  - protocol transport depends on Mcp-Session-Id and an in-memory transport Map
  - initialize remains mandatory and server/discover is absent
  - OAuth clients, codes, access tokens, and refresh tokens are process-memory state
  - workspace handles persist in SQLite but lack principal/client binding and expiry
  - build identity mixes a fixed 16-tool default surface with a dynamic 24-tool gateway manifest
```

## Scope and authority freeze

The first implementation card is deliberately limited to surface identity and
transport. It may add protocol configuration, a v2 dual-stack adapter, modern
result/header/cache/trace compatibility, tests, and build identity fields.

It must not:

- change `CapabilityPlanner`, `HybridRouteDecision`, UnifiedRuntime, P/D/X/R/A/C,
  task state, attempt identity, Candidate authority, or approval/integration logic;
- create a second task database, router, executor, receipt store, or tool manifest;
- implement the MCP Tasks extension as a new source of truth;
- persist OAuth clients/tokens or add workspace principal/TTL schema in this card;
- expose raw DevSpace edit/write/shell tools in public gateway mode;
- widen OAuth scopes, filesystem roots, shell permissions, merge/push authority,
  branch/ref deletion, credential administration, or public tunnel authority;
- modify the canonical Python Gateway to claim full MCP 2026 compatibility.

The Python Gateway remains a private JSON-RPC tool provider behind the external
adapter during this card.

## Allowed files

External implementation must start from a clean isolated checkout of
`2d1efff955a9013dfb016deca775f88cf8cdd605`; the dirty daily generated artifacts
are evidence only and must not be absorbed.

```text
/Users/jameschen/Workspace/nexus-devspace-mcp/package.json
/Users/jameschen/Workspace/nexus-devspace-mcp/package-lock.json
/Users/jameschen/Workspace/nexus-devspace-mcp/src/config.ts
/Users/jameschen/Workspace/nexus-devspace-mcp/src/config.test.ts
/Users/jameschen/Workspace/nexus-devspace-mcp/src/server.ts
/Users/jameschen/Workspace/nexus-devspace-mcp/src/mcp-transport.ts
/Users/jameschen/Workspace/nexus-devspace-mcp/src/mcp-transport.test.ts
/Users/jameschen/Workspace/nexus-devspace-mcp/src/nexus-gateway-proxy.ts
/Users/jameschen/Workspace/nexus-devspace-mcp/src/nexus-gateway-proxy.test.ts
/Users/jameschen/Workspace/nexus-devspace-mcp/src/nexus-tools.ts
/Users/jameschen/Workspace/nexus-devspace-mcp/scripts/generate-build-identity.js
/Users/jameschen/Workspace/nexus-devspace-mcp/README.md
```

Generated files may change only through the formal build/pack commands:

```text
/Users/jameschen/Workspace/nexus-devspace-mcp/generated/build-identity.json
/Users/jameschen/Workspace/nexus-devspace-mcp/generated/artifact-sha256.txt
/Users/jameschen/Workspace/nexus-devspace-mcp/dist/**
```

Ceilings: production 5, tests 3, package/lock 2, documentation 1, generated 3,
deletions 0. Any need to alter OAuth persistence, workspace schema, or canonical
Gateway code is a scope block and requires a separate card.

## Required behavior

### G0 — truthful public surface identity

- Health/build identity distinguishes `raw_devspace` from
  `canonical_gateway_proxy`; it reports protocol mode, tool source, observed
  manifest count/revision, source/artifact identity, and proxy state.
- Gateway proxy mode fetches the canonical `tools/list` manifest at startup and
  exposes exactly that deterministic ordered surface. The current expected count
  is 24, but code must bind the manifest revision rather than hard-code 24.
- Public startup fails closed when configured as canonical gateway surface but
  gateway URL/token/manifest verification is absent.
- Raw 16-tool DevSpace remains opt-in local maintenance only.

### G1 — dual-stack protocol boundary

- Upgrade from the v1 package to the exact official v2 server/node dependency
  baseline recorded above and bind it in the lockfile.
- Add `MCP_PROTOCOL_MODE=dual|legacy|modern` with `dual` as the candidate default
  and `legacy` as the immediate rollback.
- Modern requests use the official v2 HTTP handler, implement
  `server/discover`, require per-request protocol/capability metadata, and do not
  read, emit, or retain `Mcp-Session-Id`.
- Legacy requests remain compatible through the documented SDK compatibility
  path. Legacy state must not be mistaken for application workspace/task state.
- A Server restart cannot require recovery of a protocol transport Map.

### G2 — modern result and observability envelope

- Every modern result has `resultType`; legacy results remain backward
  compatible.
- List results provide required cache hints and deterministic ordering.
- Validate standard MCP request headers for modern requests.
- Propagate `request_id`, `traceparent`, `tracestate`, `baggage`, authenticated
  principal/client identity, protocol version, tool name, task ID, and attempt ID
  when present. Do not log tokens or secrets.

### G3 — disconnect/restart behavior

- Modern 20-call smoke uses no protocol session ID.
- After Server restart, an already durable `workspaceId` can resume a bounded
  read after allowed-root revalidation.
- A submitted long Nexus task survives client disconnect and can be recovered by
  existing task ID; no new task engine or state file is introduced.
- Duplicate mutation requests use existing Nexus idempotency contracts and do
  not apply twice.
- OAuth restart behavior is explicit and typed for this card
  (`REAUTH_REQUIRED` is acceptable); persistence is deferred.

## Verification

```bash
npm --prefix /Users/jameschen/Workspace/nexus-devspace-mcp run test
npm --prefix /Users/jameschen/Workspace/nexus-devspace-mcp run typecheck
npm --prefix /Users/jameschen/Workspace/nexus-devspace-mcp run build
npm --prefix /Users/jameschen/Workspace/nexus-devspace-mcp pack --json
git -C /Users/jameschen/Workspace/nexus-devspace-mcp diff --check
git -C /Users/jameschen/Workspace/nexus-devspace-mcp diff --diff-filter=D --name-status
```

Required acceptance matrix:

```text
modern server/discover negotiates 2026-07-28
modern 20 calls use zero Mcp-Session-Id headers
legacy initialize client remains functional
server restart resumes a persisted workspace read
long task reconnect returns the same task/attempt identity
duplicate mutation with the same idempotency key applies once
gateway proxy identity equals its observed manifest
raw DevSpace tools are absent from public gateway mode
OAuth restart returns an explicit typed disposition
two clean starts return the same source/artifact/manifest identity
```

## Stop conditions

Return `RECOVERABLE_BLOCK` without cutover if ChatGPT cannot negotiate the
candidate dual mode, legacy fallback fails, OAuth must be weakened, or a clean
artifact cannot be produced. Return `HARD_BLOCK` if any mutation is duplicated,
a public path exposes raw shell/edit/write tools, workspace/task recovery needs
manual state edits, a tool manifest cannot be bound exactly, or implementation
requires a second route/task/receipt authority.

## Candidate, integration, and cutover gates

The worker may produce and commit only a scoped external Candidate. Independent
acceptance must bind exact source commit, package artifact hash, protocol matrix,
tool manifest revision, auth behavior, and two-start evidence. Owner approval is
required separately for artifact install and live Connector cutover. No push,
branch/ref deletion, unrelated worktree cleanup, modern-only cutover, or
production-ready claim is authorized by this card.

## Claim ceiling

Before live cutover, the maximum claim is:

```text
DUAL_STACK_TRANSPORT_CANDIDATE_WITH_LOCAL_RESTART_AND_COMPATIBILITY_EVIDENCE
```

It does not claim OAuth durability, principal-bound workspace isolation, Tasks
extension compatibility, live ChatGPT modern negotiation, complete disconnect
elimination, production readiness, or public deployment.
