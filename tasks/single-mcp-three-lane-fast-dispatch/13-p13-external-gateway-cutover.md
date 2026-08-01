# Task Card P13: External Gateway Artifact and Connector Cutover

## Identity

- task_id: `single-mcp-three-lane-p13-external-gateway-cutover`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: VERIFIED_PENDING_OWNER_REVIEW
- owner: James Chen
- authorization: owner-approved in active continuation on 2026-08-01
- objective: Make the externally registered DevSpace runtime expose only the canonical Nexus gateway, then prove immutable identity, auth scope, two clean starts, and one GPT-visible registration.
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Allowed Files

Canonical coordination:

- `tasks/single-mcp-three-lane-fast-dispatch/INDEX.md`
- `tasks/single-mcp-three-lane-fast-dispatch/09-p9-external-connector-cutover.md`
- `tasks/single-mcp-three-lane-fast-dispatch/13-p13-external-gateway-cutover.md`

External DevSpace source (only these paths):

- `/Users/jameschen/Workspace/nexus-devspace-mcp/src/config.ts`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/src/config.test.ts`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/src/server.ts`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/src/server.test.ts`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/src/nexus-gateway-proxy.ts`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/src/nexus-gateway-proxy.test.ts`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/src/nexus-tools.ts`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/scripts/generate-build-identity.js`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/package.json`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/README.md`

Generated artifact files may change only through the formal build command:

- `/Users/jameschen/Workspace/nexus-devspace-mcp/generated/build-identity.json`
- `/Users/jameschen/Workspace/nexus-devspace-mcp/dist/**`

## Forbidden Scope

- No direct lifecycle JSON edits.
- No mutation of `/Users/jameschen/.codex/config.toml` without a separate
  explicit registration action; connector registration uses the documented
  owner/app flow.
- No package publish, push, branch deletion, or protected history rewrite.
- No changes outside the listed external paths.
- No disabling OAuth, bearer auth, or owner approval.

## Required Behavior

1. DevSpace proxy mode fetches and advertises the canonical Gateway manifest at
   runtime (currently 24 tools) and forwards JSON-RPC to the canonical loopback
   gateway; it does not maintain a second hardcoded tool/schema registry.
2. Ordinary DevSpace workspace/edit/shell tools are not exposed in proxy mode;
   the old runtime remains only as an explicitly non-public local mode.
3. Build identity binds package version, source commit, artifact hash, gateway
   commit, lifecycle commit, and tool manifest revision.
4. The artifact passes source-clean, typecheck, unit tests, and package hash
   verification before install.
5. Two clean starts return identical identity and tool manifest values.
6. Auth scopes prevent ordinary GPT access to approve/integrate/push/admin
   operations.
7. A single connector registration is verified at the owner surface; no second
   Nexus MCP registration remains.

## Verification Commands

```bash
git -C /Users/jameschen/Workspace/nexus-devspace-mcp status --short --branch
npm --prefix /Users/jameschen/Workspace/nexus-devspace-mcp run test
npm --prefix /Users/jameschen/Workspace/nexus-devspace-mcp run typecheck
npm --prefix /Users/jameschen/Workspace/nexus-devspace-mcp run build
npm --prefix /Users/jameschen/Workspace/nexus-devspace-mcp pack --json
```

## Exit Criteria

- External source clean at the exact committed proxy implementation.
- Installed artifact hash equals generated build identity and package tarball.
- Two fresh runtime starts produce byte-identical gateway identity.
- Connector owner surface shows exactly one Nexus gateway registration.
- Canonical Nexus remains clean, one worktree, zero actionable tasks.

## Evidence (2026-08-01)

- External implementation commit: `2d1efff955a9013dfb016deca775f88cf8cdd605`.
- `npm run test`: passed (including dynamic-manifest/proxy/config tests and the
  existing 52 assertions); `npm run typecheck`: passed; `npm run build`: passed.
- Local artifact: `nexus-local-devspace-1.0.1-nexus.3.tgz`; postpack SHA-256:
  `7155a3b777d8d04fffe3c56536eb8dcb97244edd2b0ae25c0f9ea7d769b3f3a0`.
- Build identity binds package/source plus gateway `nexus-mcp-gateway@0.1.0`,
  the exact canonical gateway/lifecycle commit at build time, and gateway tool
  manifest revision
  `6c1b0339588b313aaf3c8f30f25aa0cf72459850adc7d21b67e52bb89e9c55dd` (24
  tools). The resulting build manifest SHA-256 is
  `7e4893b107d71b8f78c96306f08783a16e6e6e9219b2f8f044a2534983e826af`.
- Installed local package reports `@nexus-local/devspace@1.0.1-nexus.3`.
- Two clean local starts returned identical proxy identity and tools-list
  evidence (`tool_count=24`, names hash `6c1b0339…`, candidate approval schema
  present). A fresh public Funnel OAuth session returned the same 24-tool
  manifest and approval schema, and a live read-only proxy call reached the
  canonical gateway.

## Closure Evidence (2026-08-01)

- The prior `nexus01` readonly report was against the superseded 10-tool
  artifact. After the 24-tool reload, a fresh ChatGPT `nexus01` reconnect and
  read/Direct/Candidate smoke is still required; synthetic public OAuth evidence
  is not substituted for that owner-surface proof.
- DevSpace logs show one fresh dynamic ChatGPT registration event followed by
  OAuth approval and five fresh MCP sessions in the 07:10-07:14 window. All
  authenticated MCP POSTs returned 200 or 202; no 5xx occurred.
- The observed public registration used the Nexus redirect URI
  `https://chatgpt.com/connector/oauth/OKJfDgDY_EZ8` and resource
  `https://jamesmacbook-pro-356.tail7657b6.ts.net/mcp`.
- Live public synthetic tools/list matches the canonical manifest; the final
  owner-surface claim remains open until `nexus01` reconnects and re-runs the
  three P7 smoke cases.
