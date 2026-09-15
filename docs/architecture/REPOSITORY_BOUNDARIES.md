# Repository Boundaries and Ownership Declaration

## Role of James3014/Nexus-new
`James3014/Nexus-new` is designated as **LEGACY_INTEGRATION_LAB** and Compatibility Host.
It is no longer the canonical implementation repository for Core, Learning, or Open SWE runtime.

## Canonical Repositories
- **nexus-core**:
  - Canonical repository: `James3014/nexus-core`
  - Scope: Evidence Trust Core, Completion Core, ChangeSet certification, standalone `nexus-certify` CLI.
- **nexus-open-swe-runtime**:
  - Canonical repository: `James3014/nexus-open-swe-runtime`
  - Scope: External Open SWE / Deep Agents execution runtime, transport, and tools.
- **nexus-learning**:
  - Canonical repository: `James3014/nexus-learning`
  - Scope: Evidence-bounded learning episodes, closure evaluation, coverage probes, recommendation schemas.

## Legacy Paths Disposition in Nexus-new
The following in-tree paths in `Nexus-new` are frozen:
- `product/`: `LEGACY_COMPATIBILITY_SNAPSHOT` (NO_NEW_FEATURE_DEVELOPMENT)
- `runtimes/open_swe/`: `LEGACY_COMPATIBILITY_SNAPSHOT` (NO_NEW_FEATURE_DEVELOPMENT)
- `nexus/learning/`: `LEGACY_COMPATIBILITY_SNAPSHOT` (NO_NEW_FEATURE_DEVELOPMENT)

All new feature development for these domains must take place in their respective canonical repositories.
