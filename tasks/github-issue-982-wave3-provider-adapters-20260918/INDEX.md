# Issue #982 Wave 3 Provider Enforcement Adapters

artifact_authority: current
status: ACTIVE
owner: James Chen
AUTO_CHAIN: false

## Current frontier

- Durable owner: `James3014/Nexus-new#982`
- Wave 1 authority foundation: canonical on Nexus-new main.
- Wave 2 DevSpace foundation: merged by PR `James3014/devspace#191`; canonical main `3117cce75da90df1a2523b690e7c0cc5c47045f9`.
- Wave 3 source base is rebound to DevSpace canonical main `3117cce75da90df1a2523b690e7c0cc5c47045f9`.
- Target state: provider-adapter source implementation + focused tests, then STOP before physical 11-model canary / benchmark.

## Dependency frontier

1. DevSpace source mutation must start from exact canonical main `3117cce75da90df1a2523b690e7c0cc5c47045f9`.
2. OMP/OpenCode may claim source-level native enforcement only where exact adapter tests prove emitted native restrictions.
4. Codex/Grok/Agy/Cline must fail closed or remain explicitly unsupported for enforced projections when no current physical per-tool restriction seam is proven.
5. Physical exposure receipts and 11-model canaries remain a later gate.
