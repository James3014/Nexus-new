---
title: Wiki Link Health Report
type: report
status: active
lifecycle: current
authority: operational
owner: nexus-core
verified_at: '2026-07-13'
verified_against_commit: 957cd19c744d168ff050667b611adca5fb20d56f
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

## Wiki linter command

```
wiki_linter_command_not_verified
```

No verified Wiki linter command was found in the repository. The `scripts/ops/wiki_linter.py` file exists but its invocation was not confirmed for dry-run mode.
