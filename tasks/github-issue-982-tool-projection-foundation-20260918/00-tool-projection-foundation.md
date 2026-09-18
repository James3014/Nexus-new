# Task Card: Issue #982 G2 Tool Projection Foundation

artifact_authority: current
task_id: `issue-982-g2-tool-projection-foundation-20260918`
owner: James Chen
status: ACTIVE
contract_kind: TRACKED_TASK_CARD
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Objective

Implement only the DevSpace canonical foundation frozen by Issue #982 G1B/G1C: one transport-neutral, authority-bound, content-addressed ToolProjectionManifest contract and the existing ExecutionBinding.capabilities.toolManifestRef wiring. Stop before provider adapters, physical canaries, or benchmark work.

## Source fence

- Nexus-new canonical main at compilation: `ad29eb7e1af7f5c1e0919837ba89556b29a5ba19`
- DevSpace canonical main at compilation: `d0a616d2abdb13a08cdbd6e9e890a6ab9f4a7e9e`
- Durable owner: `James3014/Nexus-new#982`
- G1C design boundary: `devspace.tool_intent.v1` + `devspace.tool_projection_manifest.v1`
- Reuse target: existing `ExecutionBinding.capabilities.toolManifestRef`

## Allowed DevSpace mutation scope

- `src/execution-protocol.ts`
- `src/execution-protocol.test.ts`
- `src/local-agent-contract.ts`
- `src/local-agent-execution-contract.test.ts`

Maximum changed files: 4. No provider adapter file is authorized.

## Required behavior

1. Canonical tool intent IDs are transport-neutral:
   - `workspace.read`
   - `workspace.search_text`
   - `workspace.search_paths`
   - `workspace.list`
   - `workspace.mutate`
   - `process.execute`
2. Enforce `selectedTools ⊆ candidateTools ⊆ authorizedToolCeiling`.
3. Canonical set fields are deduplicated and lexicographically sorted for order-independent identity.
4. If order affects selection, represent it explicitly with an order-sensitive field rather than hidden array order.
5. ToolProjectionManifest is carried by value in the execution contract and identified by SHA-256 content address.
6. `ExecutionBinding.capabilities.toolManifestRef` must equal the exact computed manifest reference when a manifest is supplied.
7. The manifest must not include its own hash or `executionBindingHash`; avoid circular identity.
8. OWNER_DIRECT and NEXUS_GOVERNED provenance remain separate; the manifest compiler cannot mint or widen authority.

## Negative controls

- Reject unknown canonical tool intent IDs.
- Reject duplicates or non-canonical ordering where the parser promises canonical form.
- Reject selected tools outside candidate tools.
- Reject candidate tools outside the authorized ceiling.
- Reject mismatched/tampered `toolManifestRef`.
- Reject stale task/attempt identity mismatch between execution binding and manifest.
- Do not silently drop unsupported semantics or widen to full tools.
- Do not treat `selectedTools` as proof of `actual_exposed_tools`.

## Forbidden scope

- No OMP/OpenCode/Codex/Grok/Agy/Cline adapter implementation.
- No Provider-native tool registry or second Tool Registry/SSOT.
- No CapabilityPlanner ownership of provider-native tool IDs.
- No JIT benchmark, 11-model launch, exposure receipt implementation, runtime reload, release, or production claim.
- No change to route selection, Workforce Admission, merge authority, or provider/model selection.
- No G3 or G4 work.

## Verification

Run at minimum:
- `npx tsx src/execution-protocol.test.ts`
- `npx tsx src/local-agent-execution-contract.test.ts`
- `npm run typecheck`
- `git diff --check`

Inspect the complete diff and verify changed paths are a subset of the allowed scope.

## Claim ceiling

Implementation may claim only `CANDIDATE_READY` after the required tests pass on the exact Candidate. It may not self-claim independent acceptance, merge readiness, runtime activation, G2 provider completion, G3, G4, release, or production status.

## Exit criterion

Wave 2 foundation is a Candidate only when:
- the exact frozen manifest/namespace semantics are implemented;
- `toolManifestRef` is deterministically bound and tamper-tested;
- OWNER_DIRECT / NEXUS_GOVERNED separation is preserved;
- required focused tests, typecheck, and diff check pass;
- no provider adapter file changed.

Then STOP. The next gate is provider-family enforcement adapters under a separate authority decision.
