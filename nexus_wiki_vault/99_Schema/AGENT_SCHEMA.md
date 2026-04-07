---
aliases:
- Vault Schema
- Nexus Obsidian Schema
last_updated: 2026-04-06
owner: human
status: active
title: AGENT_SCHEMA
type: schema
version_scope:
- v17.1
- v22
- v23
---



# AGENT_SCHEMA

## 1. Purpose

This vault is a compiled codebase wiki for Nexus.

It is not:
- a replacement for the repo,
- a runtime configuration source,
- a second manifest,
- a second state store,
- a deployment control surface.

It is:
- a navigable knowledge layer,
- a compiled summary of source-of-truth materials,
- a human+agent collaboration space for architecture, modules, flows, states, protocols, operations, diffs, and open conflicts.

The repo, `.nexus`, schemas, manifests, and acceptance artifacts remain the authority.

---

## 2. Source of Truth Rules

### 2.1 Primary truth
The following are authoritative:
- repository source code,
- `.nexus` artifacts,
- schema contracts,
- `manifest.json`,
- acceptance and audit artifacts,
- active specifications.

### 2.2 This vault is compiled knowledge
Pages in this vault must summarize, connect, and explain.
They must not become an independent truth source.

### 2.3 Conflict handling
If two sources disagree:
- do not silently merge,
- do not guess,
- create or update `[System - Unknowns and Conflicts](../01_System/System - Unknowns and Conflicts.md)`,
- note version scope and source path,
- mark confidence as low or medium until resolved.

---

## 3. Version Boundary Rules

### 3.1 Required positioning
All pages that mention v23 must preserve this framing:

- v22 = stable production baseline
- v23 = intelligence / governance layer built on top of v22
- v23 does not replace v22 runtime contract, acceptance gate, or production guarantees

### 3.2 Version scope is mandatory
Every page must declare one or more scopes:
- v17.1
- v22
- v23

If a page mixes versions, it must explicitly separate them.

### 3.3 No collapsed timelines
Do not write as if all versions describe the same system state.
Use:
- superseded by
- extended by
- coexists with
- unclear / unresolved

---

## 4. Folder Taxonomy

Use only these top-level folders:

- `00_Home`
- `01_System`
- `02_Modules`
- `03_Flows`
- `04_State`
- `05_Protocols`
- `06_Ops`
- `07_Diffs`
- `08_Incidents`
- `09_Roadmap`
- `90_Sources`
- `99_Schema`

### 4.1 Folder meaning
- `00_Home`: entry pages and navigation hubs
- `01_System`: overall architecture and system maps
- `02_Modules`: stable module-level pages
- `03_Flows`: runtime, orchestration, and lifecycle flows
- `04_State`: states, schemas, contracts, state machines
- `05_Protocols`: CLI, manifest, evidence, governance interfaces
- `06_Ops`: release, acceptance, CI, audit, runtime operations
- `07_Diffs`: version and architecture differences
- `08_Incidents`: important incident and RCA summaries
- `09_Roadmap`: future evolution and planned capability pages
- `90_Sources`: [Source Index](../90_Sources/Source Index.md) and source metadata only
- `99_Schema`: rules, templates, linting, agent instructions

---

## 5. Naming Rules

### 5.1 Page prefixes
Use one of these page prefixes only:

- `System - ...`
- `Module - ...`
- `Flow - ...`
- `State - ...`
- `Protocol - ...`
- `Ops - ...`
- `Diff - ...`

[[exceptions]]:
- `[System Overview](../00_Home/System Overview.md)`
- `[Source Index](../90_Sources/Source Index.md)`
- `AGENT_SCHEMA`

### 5.2 Stable naming
Do not rename pages casually.
If renaming is necessary:
- preserve old title in `aliases`
- update backlinks
- note rename in page history section if relevant

### 5.3 No raw file mirror naming
Do not create pages named after every source file by default.
Example of forbidden first-pass pages:
- `nexuscorecommander.py`
- `main.rs`
- `swarm.proto`

Those may only appear as module references unless repeated usage justifies a dedicated module page.

---

## 6. Page Types

### 6.1 Allowed page types
Each page must declare one of:
- home
- system
- module
- flow
- state
- protocol
- ops
- diff
- incident
- roadmap
- source-[index](../.nexus/nexus_wiki_vault/.nexus/graph/index.md)
- schema

### 6.2 Frontmatter template
All pages should include:

```yaml
---
title:
aliases: []
type:
status: draft
version_scope: []
source_of_truth: compiled-wiki
raw_sources: []
related_pages: []
related_modules: []
tags: [nexus]
last_compiled:
last_verified:
confidence: medium
owner: agent
---
```

### 6.3 Confidence labels
Use:
- high = directly supported by current active specs or verified artifacts
- medium = synthesized from multiple reliable sources
- low = incomplete, ambiguous, or conflict-marked

---

## 7. Required Page Structure

Every non-home page must contain these sections:

1. `## One-sentence summary`
2. `## Role / responsibility`
3. `## Upstream`
4. `## Downstream`
5. `## Related modules / files`
6. `## Source notes`
7. `## Open questions / conflicts`

### 7.1 Source notes format
Use concise bullet lines:
- source document
- why it matters
- version scope if relevant

### 7.2 Open questions
Open questions are required even if empty.
If none are known, write:
- `- None currently identified.`

---

## 8. Linking Rules

### 8.1 Double-link requirement
Every page must link to at least 2 related pages.

### 8.2 Hub linking
All major pages should link back to one of:
- `[System Overview](../00_Home/System Overview.md)`
- `[System - Unknowns and Conflicts](../01_System/System - Unknowns and Conflicts.md)`

### 8.3 Conflict backlinks
Any page with unresolved conflict must link to:
- `[System - Unknowns and Conflicts](../01_System/System - Unknowns and Conflicts.md)`

### 8.4 Source linking
Where possible, connect concept pages to:
- lifecycle pages,
- schema pages,
- operations pages,
- diff pages.

---

## 9. Source Ingestion Rules

### 9.1 Ingestion tiers
Use this order:

Tier 1:
- v22 Engine Spec
- v17.1 Hardened Spec
- v23 Wisdom / supplement docs

Tier 2:
- document lifecycle / update / audit protocols
- maintainer / CI / deployment docs

Tier 3:
- RCA
- walkthroughs
- roadmap notes
- release notes

### 9.2 Ingest behavior
When ingesting a new source:
1. update `[Source Index](../90_Sources/Source Index.md)`
2. identify affected pages
3. update only impacted summaries
4. add new conflicts if contradictions appear
5. do not rewrite the whole vault unnecessarily

### 9.3 No raw duplication
Do not paste large original source text into wiki pages.
Prefer summary + source note + link reference.

---

## 10. Lint Rules

After each compile/update pass, run a vault lint pass.

### 10.1 Required lint checks
Check for:
- orphan pages
- missing source notes
- missing version scope
- unresolved placeholder text
- naming violations
- duplicated pages with same meaning
- conflicts not linked to `Unknowns and Conflicts`
- statements that collapse v17.1/v22/v23 into one fact
- pages that imply the vault is a source of runtime truth

### 10.2 Conflict lint
If a page claims certainty while related diff/conflict pages still show ambiguity, downgrade confidence and add a conflict note.

### 10.3 Ops-specific lint
Pages about release, acceptance, manifest, schemas, or runtime truth must align with official contract language and artifact paths.

---

## 11. Forbidden Behaviors

The agent must not:
- invent modules, files, or flows
- silently reconcile conflicting versions
- treat [walkthrough](../Reference/walkthrough.md) notes as higher authority than active specs
- create a second manifest or state registry inside Obsidian
- modify runtime files from vault instructions
- turn notes into deployment instructions without source support
- describe v23 as replacing v22 production runtime
- claim learner / guard / healing behaviors without source-backed notes

---

## 12. Human Escalation Rules

Escalate to human when:
- two active sources conflict materially
- page structure is insufficient for a recurring topic
- a module seems important enough for its own dedicated page
- a runtime path is unclear
- source documents appear stale or internally inconsistent

Escalation output goes to:
- `[System - Next Questions for Human](../01_System/System - Next Questions for Human.md)`
- and, if conflict-related, also `[System - Unknowns and Conflicts](../01_System/System - Unknowns and Conflicts.md)`

---

## 13. Update Rhythm

### 13.1 Daily or per major change
- ingest changed documents
- update affected pages only
- refresh conflict register

### 13.2 Weekly
- full lint pass
- backlink check
- orphan page cleanup
- version drift review

### 13.3 Release or milestone events
On release / stabilization / promotion:
- update related ops pages
- update version diff pages
- confirm wording still preserves version boundaries
- mark if resident-state / acceptance / evidence-chain behavior changed

---

## 14. First-Pass Scope Policy

The first pass of the vault should prioritize:
- system map
- topology
- orchestrator
- runtime services
- CLI surface
- evidence chain
- PXDRAC flow
- lifecycle
- schemas
- acceptance and release
- wisdom layer
- version diff

Do not expand into fine-grained module pages until repeated user questions justify them.

---

## 15. Output Contract for the Agent

Every update cycle should end with a compact report:

1. pages created
2. pages updated
3. sources ingested
4. conflicts added
5. missing data / blocked areas
6. recommended next pages

Do not claim “complete” unless:
- source notes exist,
- version scope exists,
- backlinks exist,
- lint passes,
- major conflicts are registered.

---

## 16. Working Principle

Humans choose direction.
The agent compiles and maintains the wiki.
The vault should become easier to navigate over time, not larger for its own sake.