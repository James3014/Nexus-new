# Campaign Index: openwiki-canonical-integration-pilot-20260808

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Create the first governed OpenWiki canonical-integration pilot scaffold without integrating generated documentation. Add only: (1) .openwikiignore with Nexus-specific read-boundary exclusions including nexus_wiki_vault/, root/file symlink aliases and runtime/generated noise; (2) openwiki/INSTRUCTIONS.md with the V3 five-axis classification contract separating implementation_status, wiring_status, runtime_surfaces, authority_roles, and evidence_basis/claim_ceiling, preserving derived_non_authoritative authority and CapabilityPlanner/HybridRouteDecision route authority; (3) .github/workflows/openwiki-update.yml as a manual-only workflow_dispatch pilot pinned to openwiki@0.3.1, telemetry disabled, Gemini AI Studio via the repository's existing GEMINI_API_KEY secret convention, no schedule, no repository write permission, no commit/push/PR, and no generated Wiki integration. The workflow may generate OpenWiki output only as an ephemeral artifact, must restore AGENTS.md, CLAUDE.md, and its own workflow file to HEAD after generation, must fail closed if any repository path outside openwiki/ changes, and must never modify nexus_wiki_vault/. Do not run OpenWiki against canonical during implementation. Do not commit generated Wiki pages. AUTO_CHAIN=false. No approval, integration, push, cleanup, production/public claim, or successor task execution.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `OPENWIKI-INTEGRATION-PILOT-01` | `00-OPENWIKI-INTEGRATION-PILOT-01.md` | ACTIVE | Owner confirmation |
