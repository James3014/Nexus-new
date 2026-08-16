---
id: 01-repair-six-skill-descriptors
campaign_id: github-issue-152-skill-descriptor-repair
status: COMPLETE
source_issue: https://github.com/James3014/Nexus-new/issues/152
baseline_main: 70fd467ab0d29f4373616a5e98d85b014efcd4de
historical_baseline: 70fd467ab0d29f4373616a5e98d85b014efcd4de
merge_base: 96f2c8a19a2f3d208a106fa1850bee7ce5a4e863
historical_reconciled_main: cdf2570ede5ae218f36f886b696c8da45458043a
reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
current_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
frontier_status: TERMINAL_RECONCILIATION
terminal_marker: SIX_SKILL_DESCRIPTOR_CONTRACTS_REPAIRED
claim_ceiling: SIX_SKILL_DESCRIPTOR_CONTRACTS_REPAIRED_ONLY
block_class: NONE
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

## Physical evidence and terminal boundary

- Historical card baseline: `70fd467ab0d29f4373616a5e98d85b014efcd4de`.
- PR #154 head: `971c2e99d211f263dfdb1e590025ab404d6ab6f1`.
- PR #154 merge: `0b97df90bbebbd90d0811d46ba73c47e46fe1878`.
- Exact scope: the six descriptor paths above plus this card and INDEX.
- Exact-head workflows: Pytest, Pyright, Bandit, Ruff, and Wiki governance completed
  successfully.
- Owner receipt: `SIX_SKILL_DESCRIPTOR_CONTRACTS_REPAIRED`.
- Historical reconciled current main: `cdf2570ede5ae218f36f886b696c8da45458043a`
  (earlier historical `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`).
- Reconciled current main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
  (prior reconciled main `cdf2570ede5ae218f36f886b696c8da45458043a`).

The GitHub review surface for PR #154 is empty, so this reconciliation does not claim a
recorded GitHub independent review. `SIX_SKILL_DESCRIPTOR_CONTRACTS_REPAIRED` is
limited to descriptor frontmatter validity, unchanged bodies, and Yang's stable id. No
runtime eligibility, catalog promotion, selector/workflow change, approval, integration,
merge, release, or production claim follows. `AUTO_CHAIN=false`.
