# Nexus SF Current Capability-Skill Status - 2026-05-18

## Closure Level
- SF V7 catalog pairing: PASS; every SF capability bucket has a primary or alternate recommendation.
- Runtime default apply: HOLD; manual apply review ready, auto-apply disabled.
- Public benchmark: HOLD; not part of SF completion.

## Primary Pairings
- `forecast_pregate` -> primary `create-plan`; verdict `replace_candidate`; alternates `none`.
- `governance_and_trust` -> primary `acceptance-evidence-failclosed`; verdict `catalog_primary_selected_runtime_hold`; alternates `cso, claudeosint-safe-surface-audit, gbrain-soul-audit`.
- `repair_and_coding` -> primary `TBD`; verdict `alternate_candidate`; alternates `tdd`.
- `repair_loop` -> primary `tdd`; verdict `replace_candidate`; alternates `none`.
- `research_and_source_discipline` -> primary `research-citation-chain-verifier`; verdict `replace_candidate`; alternates `research-source-validation-auditor`.

## SF2 Route-Capability Static Coverage
- route_capability_count: 33
- capabilities_with_static_fit_candidate: 33
- blocked_capability_count: 0
- Meaning: broad route-capability discovery is covered at static-fit level; only SF V7 primary buckets have receipt-backed/tie-break closure.

## New Skill Update Flow
1. Register/ingest source as candidate intake only.
2. Classify candidate into capability bucket(s).
3. Screen source/status/security/license metadata; quarantine or reject unsafe candidates.
4. Build capability-only vs skill-arm matrix plus negative control.
5. Run bounded Flash+Nexus comparison when live evidence is required: same session contract, without skill vs with skill.
6. Count only receipt-backed selected/injected/used/evidence/gate/outcome rows.
7. Write `(capability, skill_id)` verdict to catalog and replacement ledger.
8. Keep runtime default unchanged until separate apply gate and smoke pass.
