# Issue #982 Wave 3 Provider Enforcement Adapters

artifact_authority: current
status: PREPARED_NOT_CANONICAL
owner: James Chen
AUTO_CHAIN: false

## Current frontier

- Durable owner: `James3014/Nexus-new#982`
- Wave 1 authority foundation: canonical on Nexus-new main.
- Wave 2 DevSpace foundation: PR `James3014/devspace#191`, exact head `03311af01bdf85a9a0d906004ec4bad58cbda58c`.
- Wave 3 may become ACTIVE only after #191 is merged and this branch is rebound to the resulting DevSpace canonical main SHA.
- Target state: provider-adapter source implementation + focused tests, then STOP before physical 11-model canary / benchmark.

## Dependency frontier

1. #191 must be merged and the resulting DevSpace main SHA must be read back.
2. Replace the pending DevSpace base fence in the Task Card with that exact SHA before this authority Candidate is merged.
3. OMP/OpenCode may claim source-level native enforcement only where exact adapter tests prove emitted native restrictions.
4. Codex/Grok/Agy/Cline must fail closed or remain explicitly unsupported for enforced projections when no current physical per-tool restriction seam is proven.
5. Physical exposure receipts and 11-model canaries remain a later gate.
