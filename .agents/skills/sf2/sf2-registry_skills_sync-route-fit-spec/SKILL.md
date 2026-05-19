---
name: sf2-registry_skills_sync-route-fit-spec
description: Use when Nexus route capability is registry_skills_sync and the task needs skill registry sync, catalog maintenance, plugin/source refresh, and candidate intake evidence; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata:
  capability_id: registry_skills_sync
  sf2_candidate_only: true
  runtime_eligible: false
  public_benchmark_allowed: false
---

# sf2-registry_skills_sync-route-fit-spec

## Load when
SF2 spec candidate for registry_skills_sync: skill registry, plugin sync, and catalog maintenance. Use when route capability is registry_skills_sync. Required route terms: skill registry, registry, plugin, install, catalog, sync.

## Do not load when
- Runtime default mounting is requested.
- Public benchmark or production policy update is requested.
- The task does not match the declared capability_id.

## Evidence required
- Capability-only baseline row.
- Skill-arm row with selected/injected/used/evidence/outcome receipt.
- Negative-control row that BLOCKs or RETURNs.
- Runtime promotion review after SF2 verdict.

## Boundary
This asset is candidate-only. It may be used for SF2 ablation planning, but it must not be treated as a runtime skill default.
