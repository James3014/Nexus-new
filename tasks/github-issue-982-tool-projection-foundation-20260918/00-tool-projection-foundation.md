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

Implement only the DevSpace G2 canonical foundation supported by the source-rebound G1C correction: persist the exact authorized tool ceiling in the existing durable/replay-bound `ExecutionContract`, define a transport-neutral derived `ToolProjectionManifest`, and keep the existing `ExecutionBinding.capabilities.toolManifestRef` as a compatibility/content-identity reference rather than a second authority owner. Stop before provider adapters, production JIT producer wiring, physical canaries, or benchmark work.

## Source fence

- Nexus-new canonical main at compilation: `ad29eb7e1af7f5c1e0919837ba89556b29a5ba19`
- DevSpace canonical main at compilation: `d0a616d2abdb13a08cdbd6e9e890a6ab9f4a7e9e`
- Durable owner: `James3014/Nexus-new#982`
- Source-rebound authority seam: persisted/replay-bound `ExecutionContract`
- Canonical namespace: `devspace.tool_intent.v1`
- Projection schema: `devspace.tool_projection_manifest.v1`
- Compatibility/content identity reference: existing `ExecutionBinding.capabilities.toolManifestRef`

## Allowed DevSpace mutation scope

- `src/execution-protocol.ts`
- `src/execution-protocol.test.ts`
- `src/local-agent-contract.ts`
- `src/local-agent-execution-contract.test.ts`

Maximum changed files: 4. No provider adapter file is authorized.

## Required behavior

1. `ExecutionContract` is the single durable/replay-bound authority carrier for `authorizedToolCeiling`; `ToolProjectionManifest` is derived evidence and cannot mint, infer, or widen that ceiling.
2. Canonical tool intent IDs are transport-neutral: `workspace.read`, `workspace.search_text`, `workspace.search_paths`, `workspace.list`, `workspace.mutate`, `process.execute`.
3. Canonicalize the ceiling as an immutable set identity: reject unknown IDs and duplicates, and use deterministic lexicographic ordering for hashing/serialization.
4. Define projection semantics enforcing `selectedTools ⊆ candidateTools ⊆ authorizedToolCeiling`. The foundation may validate/construct a projection from explicit inputs; it must not invent a production JIT producer that current source does not establish.
5. Bind manifest identity to task/attempt and authority mode/provenance without collapsing OWNER_DIRECT into NEXUS_GOVERNED. OWNER_DIRECT must not fabricate Nexus/Planner lineage; NEXUS_GOVERNED must not substitute Owner-direct evidence.
6. A projection is content-addressed with SHA-256. If `ExecutionBinding.capabilities.toolManifestRef` is populated, it is an exact reference to projection bytes/content identity and must not become the only durable tool authority.
7. Avoid circular identity: the manifest does not contain its own hash or `executionBindingHash`.
8. If ordering affects selection, make that ordering explicit and hash-bound; hidden input-array order must not alter an order-independent set identity.
9. Missing, stale, mismatched, or widened tool authority/projection fails closed. There is no implicit full-provider-tool fallback.
10. Preserve the existing distinction: `selectedTools` is desired projection, not proof of `actualExposedTools`.

## Negative controls

- Reject unknown or duplicate canonical tool intent IDs.
- Reject selected tools outside candidate tools.
- Reject candidate tools outside the authorized ceiling.
- Reject mismatched task/attempt or authority-mode identity.
- Reject mismatched/tampered content-addressed manifest reference when a binding is constructed.
- Reject OWNER_DIRECT + Nexus-grant/provenance conflation.
- Reject NEXUS_GOVERNED substitution with Owner-direct provenance.
- Do not silently synthesize, alias, drop, or widen tools.
- Do not treat `selectedTools` as proof of physical exposure.

## Forbidden scope

- No OMP/OpenCode/Codex/Grok/Agy/Cline adapter implementation.
- No production `jit_all_tools` producer invention or Nexus producer-lineage change.
- No second Tool Registry, ToolAuthorityStore, manifest store, or parallel writable tool-scope SSOT.
- No CapabilityPlanner ownership of provider-native tool IDs.
- No 11-model launch, actual-exposure receipt implementation, benchmark, runtime reload, release, or production claim.
- No route selection, Workforce Admission, merge-authority, or provider/model-selection change.
- No G3 or G4 work.

## Verification

Run at minimum:
- `npx tsx src/execution-protocol.test.ts`
- `npx tsx src/local-agent-execution-contract.test.ts`
- `npm run typecheck`
- `git diff --check`

Inspect the complete diff and verify changed paths are a subset of the allowed scope.

## Claim ceiling

Implementation may claim only `CANDIDATE_READY` for the G2 foundation after required tests pass on the exact Candidate. It may not claim provider enforcement, production JIT wiring, independent acceptance, merge readiness, runtime activation, G3, G4, release, or production status.

## Exit criterion

Wave 2 foundation is a Candidate only when the exact durable authority seam and projection primitives above are implemented and negative-tested, the four-file scope is respected, and focused tests/typecheck/diff-check pass. Then STOP. Provider-family enforcement adapters and production selected-tool producer wiring remain later gates under separate authority.
