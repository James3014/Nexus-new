---
id: 01-repair-six-skill-descriptors
campaign_id: github-issue-152-skill-descriptor-repair
status: active
source_issue: https://github.com/James3014/Nexus-new/issues/152
baseline_main: 70fd467ab0d29f4373616a5e98d85b014efcd4de
block_class: RECOVERABLE_BLOCK
AUTO_CHAIN: false
---

# Issue 152 — bounded descriptor repair

## Objective

Repair only the six current repository skill descriptor frontmatters while
preserving every Markdown body and Yang's stable loader identity.

## Allowed files

- `.agents/skills/sf-systematic-challengers/sf-systematic-file_lock_security_gate-azure-diagnostics-e9330260/SKILL.md`
- `.agents/skills/sf-systematic-challengers/sf-systematic-repair_loop-tailwind-v4-shadcn-7197cbbf/SKILL.md`
- `.agents/skills/sf2/sf2-ddtree-route-fit-spec/SKILL.md`
- `.agents/skills/sf2/sf2-ui_validator-route-fit-spec/SKILL.md`
- `.agents/skills/sf2/sf2-xray-route-fit-spec/SKILL.md`
- `.agents/skills/yang-ding-yi-nexus-eternal/SKILL.md`
- this `INDEX.md` and Task Card

## Forbidden files/scope

No other skill, `agents/openai.yaml`, runtime, catalog, selector, workflow,
Issue #150, PR #138, loader, route, workforce, lifecycle, approval, merge,
release, or production changes.

## Exact repairs

- Quote/fold only the two malformed YAML descriptions.
- Add minimal frontmatter to the three `sf2` files with directory-matching
  `name`, candidate-only description, and `runtime_eligible: false`; preserve
  each existing body byte-for-byte.
- Yang frontmatter must use `id: nexus-yang-ding-yi-eternal-v5` and
  `name: yang-ding-yi-nexus-eternal`; preserve the body and stable loader id.

## Verification

- Parse all six frontmatters as YAML and require non-empty name/description.
- Require each name to equal its directory basename.
- Verify Yang id equals `nexus-yang-ding-yi-eternal-v5`.
- Verify body hashes are unchanged for all six files.
- Run exact six-path descriptor validation, `git diff --check`, and scope /
  deletion audit.

## Exit / claim ceiling

Candidate only: `SIX_SKILL_DESCRIPTOR_CONTRACTS_REPAIRED_CANDIDATE_ONLY`.
No runtime eligibility, catalog promotion, integration, release, or
production claim.
