# Task Card: Issue #982 Wave 4 MCP Schema Closure Repair

artifact_authority: current
task_id: `issue-982-wave4-mcp-schema-closure-20260918`
owner: James Chen
status: ACTIVE
contract_kind: TRACKED_TASK_CARD
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Objective

Repair the Wave 4 closure blocker found by independent audit: the current registered `agent_start.executionContract` MCP input schema does not expose the already-implemented `authorizedToolCeiling` and `toolProjectionManifest` fields. Expose those existing contracts without changing their authority semantics, make runtime capability evidence require them, and add regression tests proving the public MCP entrypoint can transport them into the existing parser/manager path.

## Source fence

- Nexus-new authority base: `976bac72faaf63b13ada07fe10dbe0fc6691f731`
- DevSpace implementation base: `8b5bd410907a6267459d4d05ec44853abfa1a8ed`
- First repair Candidate: `d9c823ef080b4fbf383851cf689e32b24d560590`, merged by DevSpace PR #193 into `06d758032ed2f73505cf16073cd5f42abe98f810`.
- Post-merge CI found consumer-fixture drift: `capability-generation-convergence.test.ts` failed because its authoritative-role fixture still advertised the pre-repair capability set; bounded sweep found the same stale set in `git-integration.test.ts`, which is loaded by `git-integration-ci.test.ts`.
- Durable issue owner: `James3014/Nexus-new#982`
- Existing durable authority: `ExecutionContract.authorizedToolCeiling`
- Existing projection schema: `devspace.tool_projection_manifest.v1`
- Existing namespace: `devspace.tool_intent.v1`
- Existing provider behavior from Wave 3 must not be changed.

## Allowed DevSpace mutation scope

- `src/execution-protocol.ts`
- `src/server.ts`
- `src/server.test.ts`
- `src/capability-manifest.ts`
- `src/capability-manifest.test.ts`
- `src/deployment-convergence.ts`
- `src/deployment-convergence.test.ts`
- `src/capability-generation-convergence.test.ts`
- `src/git-integration.test.ts`

Maximum changed files: 9.

## Required behavior

1. Export/reuse one canonical ToolIntent ID list from the existing execution protocol; do not copy a second writable list into the MCP server.
2. `agent_start.executionContract` publicly exposes optional `authorizedToolCeiling` and `toolProjectionManifest`.
3. The model-facing manifest schema is transport-neutral and uses the existing constants/intent IDs. It represents task/attempt, authority mode/issuer, authorized/candidate/selected sets, ordering mode, and optional explicit candidate order.
4. Relational invariants such as subset, authority-mode/issuer agreement, task/attempt agreement, canonicalization, and content identity remain enforced by the existing `parseExecutionContract` / `parseToolProjectionManifest` path. The MCP schema must not create a parallel semantic validator/authority.
5. An actual `agent_start` tool invocation through the registered server schema can carry the two fields through to the existing execution-contract parser/manager path in tests.
6. Loaded capability manifest adds:
   - `agent_start.executionContract.authorizedToolCeiling`
   - `agent_start.executionContract.toolProjectionManifest`
7. Deployment convergence treats both new capabilities as required for the authoritative production role, so a live build missing the public contract cannot be called converged for this capability generation.
8. Existing no-projection callers remain backward compatible.
9. Consumer fixtures that intentionally represent a converged authoritative DevSpace runtime must advertise the full canonical required capability set, including the two new tool-projection capabilities. Fixtures intentionally testing missing/stale capabilities must remain intentionally incomplete.
10. No provider adapter semantics change in this repair.

## Negative controls

- Removing either field from the registered schema must make the capability manifest report it missing.
- Provider-native IDs must not become valid ToolIntent IDs.
- The public schema may expose structure, but cannot widen or replace the durable ceiling.
- Existing parser negative controls for widening, authority mismatch, task mismatch, and tampering must remain green.
- A build that lacks either new capability must fail deployment convergence rather than produce a false green.

## Verification

At minimum:
- `npx tsx src/execution-protocol.test.ts`
- `npx tsx src/local-agent-execution-contract.test.ts`
- relevant `src/server.test.ts` agent_start schema/transport tests
- `npx tsx src/capability-manifest.test.ts`
- `npx tsx src/deployment-convergence.test.ts`
- `npx tsx src/capability-generation-convergence.test.ts`
- `npx tsx src/git-integration-ci.test.ts`
- full `npm test` or equivalent CI matrix evidence proving no stale consumer fixture remains
- `npm run typecheck`
- `git diff --check`
- changed-path audit against this nine-file scope

After merge, Wave 4 closure additionally requires live runtime readback showing the merged source/build and both new loaded capabilities.

## Forbidden scope

- No OMP/OpenCode/Codex/Grok/Agy/Cline adapter changes.
- No JIT producer implementation.
- No second Tool Registry, ToolAuthorityStore, manifest store, or planner authority.
- No G3 physical 11-model canary.
- No actual-exposed-tools receipt implementation.
- No G4 benchmark.
- No release/production claim beyond exact live DevSpace source/build/capability readback required for Wave 4 closure.

## Claim ceiling

Implementation may claim only a repair Candidate. Wave 4 closes only after independent post-merge verification and exact live runtime/build/capability rebind.

## Exit criterion

The repair is complete when the registered `agent_start` schema can carry the existing tool authority/projection contract, capability/convergence evidence requires those fields, all bounded tests pass on the exact Candidate, the change is merged, and a fresh live DevSpace readback proves the merged source/build plus both capabilities. Then STOP before G3/G4.

## Scope amendment — post-merge CI consumer drift

This amendment does not widen production behavior. It authorizes only the two test consumers discovered after the first repair merged. Their purpose is to keep convergence/promotion fixtures synchronized with the canonical capability contract. No additional production source, provider adapter, routing, JIT, or runtime authority is added.
