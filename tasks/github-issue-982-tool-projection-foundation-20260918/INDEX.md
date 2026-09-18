# Issue #982 G2 Tool Projection Foundation

artifact_authority: current
status: ACTIVE
owner: James Chen
AUTO_CHAIN: false

## Current frontier

- Durable owner: `James3014/Nexus-new#982`
- Active Task Card: `00-tool-projection-foundation.md`
- Nexus-new source fence at compilation: `ad29eb7e1af7f5c1e0919837ba89556b29a5ba19`
- DevSpace implementation base: `d0a616d2abdb13a08cdbd6e9e890a6ab9f4a7e9e`
- Durable tool-authority seam: `ExecutionContract.authorizedToolCeiling`
- Derived projection: `devspace.tool_projection_manifest.v1`
- Target state: `G2 canonical foundation Candidate + tests`
- Stop before production JIT producer wiring, provider adapters, G3, and G4.

## Dependency frontier

1. This Task Card must be tracked on canonical Nexus-new main before governed Wave 2 mutation begins.
2. Wave 2 implementation must remain within the four allowed DevSpace files.
3. The current production producer lineage for Nexus-governed candidate/selected tools remains outside this foundation and must not be invented here.
4. Independent verification/acceptance remains separate from implementation.
5. Provider adapters and physical exposure receipts require later gates and separate scope.
