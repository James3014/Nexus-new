---
title: Wiki Link Health Report
type: report
status: active
lifecycle: current
authority: operational
owner: nexus-core
verified_at: '2026-07-13'
content_verified_against_commit: a2ae57ab96a9ddb0243858f4f2c1776709511af5
document_updated_in_commit: fecda71e417c453a7ea2ae0229478784921c362a
---

# Wiki Link Health Report

## Scan scope

Scanned the 7 canonical entry-layer pages and their first-degree outgoing links.

### Pages scanned

| # | File |
|---|------|
| 1 | `README.md` |
| 2 | `00_Home/CURRENT_STATE.md` |
| 3 | `00_Home/AGENT_BOOTSTRAP.md` |
| 4 | `00_Home/PARTNER_ONBOARDING.md` |
| 5 | `01_System/CLAIM_TAXONOMY.md` |
| 6 | `00_Home/System Overview.md` |
| 7 | `00_Home/Wiki Index and Coverage Map.md` |

## Links scanned

- Total outgoing markdown links across 7 canonical pages: 38
- Links to new WIKI-1 canonical pages: 22
- Links to existing Wiki pages: 12
- Links to external docs paths: 4

## Confirmed broken links

| File | Line | Target | Status |
|------|------|--------|--------|
| `00_Home/Wiki Index and Coverage Map.md` | 48 | `../../docs/arch/CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29.md` | **REPAIRED** - corrected to `../09_Roadmap/CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29.md` |

## Repaired links

| File | Line | Old target | New target |
|------|------|-----------|------------|
| `00_Home/Wiki Index and Coverage Map.md` | 48 | `../../docs/arch/CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29.md` | `../09_Roadmap/CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29.md` |

## Verified links (all resolve)

All links in the 7 canonical pages resolve to existing files:
- `README.md` -> all 10 links resolve
- `CURRENT_STATE.md` -> no outgoing links (all references are inline)
- `AGENT_BOOTSTRAP.md` -> 5 links resolve
- `PARTNER_ONBOARDING.md` -> 10 links resolve
- `CLAIM_TAXONOMY.md` -> no outgoing links (all references are inline)
- `System Overview.md` -> persona pages exist (README_Product, README_Investor)
- `Wiki Index and Coverage Map.md` -> 3 external doc links (2 OK, 1 repaired)

## Ambiguous links

None detected in the canonical layer.

## Deferred links

The following links in the existing System Overview and Wiki Index point to older pages that were not scanned in this pass (first-degree only, not canonical):

- `00_Home/README_Product` (exists, not scanned for content)
- `00_Home/README_Investor` (exists, not scanned for content)
- `99_Schema/Wiki_Changelog_Auto` (not verified)
- `01_System/ADR/` (directory reference, not a direct file link)
- `05_Protocols/` references (not verified)

These are deferred to a broader Wiki integrity pass beyond WIKI-3 scope.

## False positives from parser limitations

The `rg` regex scan for `\]\(` does not distinguish between:
- Actual markdown links
- Links inside code blocks
- Links in YAML frontmatter aliases

No false positives were found in the canonical pages (none of the new pages contain code-block links or frontmatter alias links with markdown syntax).

## WIKI-5 physical verification findings

### Code paths verified in SYSTEM_MAP.md, TASK_ROUTER.md, GLOSSARY.md, CURRENT_STATE.md

| Documented path | Physical status | Corrected to |
|-----------------|----------------|---------------|
| `scripts/nexus_cli.py` | EXISTS | (no change - public wrapper) |
| `scripts/engine/nexus_cli.py` | EXISTS | (no change - canonical implementation) |
| `scripts/core/skills_router.py` | EXISTS | (was incorrectly `nexus/engine/skills_router.py`) |
| `nexus/core/campaign_general.py` | EXISTS | (was incorrectly `nexus/engine/campaign_general.py`) |
| `nexus/engine/capability_planner.py` | EXISTS | (no change) |
| `nexus/engine/pipeline.py` | EXISTS | (no change) |
| `nexus/core/capability_selector.py` | EXISTS | (primary; engine/ is compatibility shim) |
| `nexus/services/local_heal/local_model_executor.py` | EXISTS | (was incorrectly `nexus/engine/local_model_executor.py`) |
| `nexus/services/local_heal/committee_orchestrator.py` | EXISTS | (was incorrectly `nexus/engine/committee_orchestrator.py`) |
| `nexus/services/local_heal/isolated_verifier.py` | EXISTS | (was incorrectly `nexus/core/verifier.py`) |
| `nexus/services/local_heal/claim_delivery_gate.py` | EXISTS | (was incorrectly `nexus/core/claim_gate.py`) |
| `nexus/services/local_heal/learning_closure_bridge.py` | EXISTS | (was incorrectly `nexus/services/learning_closure.py`) |
| `nexus/services/local_heal/isolated_local_solve_loop.py` | EXISTS | (was incorrectly `nexus/core/candidate_isolation.py`) |
| `nexus/services/cloud_agent_cli_adapter.py` | EXISTS | (was incorrectly `nexus/services/cloud_agent_adapter.py`) |
| `nexus/orchestrator/evidence_collector.py` | EXISTS | (was incorrectly `nexus/core/evidence_bundle.py`) |
| `scripts/ops/wiki_sync_check.py` | EXISTS | (no change) |
| `scripts/ops/ci_gate.py` | EXISTS | (no change) |
| `nexus/engine/skills_router.py` | MISSING | No such file; skills_router is at `scripts/core/skills_router.py` |
| `nexus/engine/local_model_executor.py` | MISSING | No such file; executor is at `nexus/services/local_heal/local_model_executor.py` |
| `nexus/core/verifier.py` | MISSING | No such file; verifier is at `nexus/services/local_heal/isolated_verifier.py` |
| `nexus/core/claim_gate.py` | MISSING | No such file; claim gate is at `nexus/services/local_heal/claim_delivery_gate.py` |
| `nexus/core/evidence_bundle.py` | MISSING | No such file; evidence is at `nexus/orchestrator/evidence_collector.py` |
| `nexus/core/receipt.py` | MISSING | No such file; receipt is at `nexus/core/receipt_causality_contract.py` |
| `nexus/services/learning_closure.py` | MISSING | No such file; learning closure is at `nexus/services/local_heal/learning_closure_bridge.py` |
| `nexus/engine/committee_orchestrator.py` | MISSING | No such file; committee is at `nexus/services/local_heal/committee_orchestrator.py` |
| `nexus/services/cloud_agent_adapter.py` | MISSING | No such file; adapter is at `nexus/services/cloud_agent_cli_adapter.py` |
| `nexus/core/candidate_isolation.py` | MISSING | No such file; isolation is at `nexus/services/local_heal/isolated_local_solve_loop.py` |

### Path count summary

| Metric | Count |
|--------|-------|
| Documented path rows (EXISTS) | 17 |
| Documented path rows (MISSING legacy) | 10 |
| Total documented path rows | 27 |
| Verified caller relationships | 12 |
| Unresolved authority collisions | 3 |

Physical file existence has been checked for all 27 documented paths. Caller and authority relationships remain only partially verified: 12 verified caller relationships across 16 mapped components. Three authority collisions remain unresolved and require architecture decisions.

### Unresolved authority collisions

| Collision | Status |
|-----------|--------|
| Verifier stacks: World C vs domain verifiers | Unresolved |
| Claim gate: claim_delivery_gate.py vs concept spanning multiple files | Unresolved |
| Evidence: collector vs policy split | Unresolved |

## Wiki linter command

```
wiki_linter_command_not_verified
```

No verified Wiki linter command was found in the repository. The `scripts/ops/wiki_linter.py` file exists but its invocation was not confirmed for dry-run mode.
