# Issue #982 Wave 4 MCP Schema Closure Repair

artifact_authority: current
status: ACTIVE
owner: James Chen
AUTO_CHAIN: false

## Current frontier

- Durable owner: `James3014/Nexus-new#982`
- Nexus-new authority base: `976bac72faaf63b13ada07fe10dbe0fc6691f731`
- DevSpace original repair base: `8b5bd410907a6267459d4d05ec44853abfa1a8ed`
- First repair merged DevSpace main: `06d758032ed2f73505cf16073cd5f42abe98f810`
- Post-merge CI exposed stale required-capability fixtures in `capability-generation-convergence.test.ts` and `git-integration.test.ts`; this amendment authorizes only those test-consumer updates.
- Live DevSpace source/build observed before repair: `8b5bd410907a6267459d4d05ec44853abfa1a8ed` / `devspace-1.0.7-8b5bd410`
- Wave 4 independent audit proved the internal G2 contract and adapters are merged and tested, but the registered `agent_start.executionContract` MCP schema does not expose `authorizedToolCeiling` or `toolProjectionManifest`.
- Target state: close only this public-schema/runtime-reachability gap, then repeat independent source/runtime closure evidence.
- Stop before G3 physical canaries and G4 benchmark work.

## Dependency frontier

1. Preserve `ExecutionContract.authorizedToolCeiling` as the sole durable tool-scope authority.
2. Reuse the existing `devspace.tool_intent.v1` and `devspace.tool_projection_manifest.v1`; no second schema/registry authority.
3. Registered MCP schema, capability manifest, and deployment-convergence required-capability list must agree.
4. Full CI/test-matrix evidence must be green after all consumers are synchronized; a focused-test-only green is insufficient for Wave 4 closure.
5. A merged source fix is not Wave 4 closure until the live DevSpace build is rebound to the merged source and exposes the new capabilities.
6. G3/G4 remain separate successor gates.
