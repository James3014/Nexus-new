# Nexus Skill Inventory And Mount Contract - 2026-05-15

## Goal

整理分散在多個 agent runtime 的 Skill，先建立可審計 inventory，再定義 Nexus capability 如何掛載 Skill。

核心原則：

- Nexus 保留 capability router 作主路由。
- Skill 不做另一套平行全域路由。
- Skill 作為 capability 底下可替換、可審計、可評測的策略/上下文模組。
- 外部 runtime 的 Skill 先只讀盤點，不搬移、不刪除、不改寫。

完整機器可讀 inventory：

- `docs/reports/NEXUS_SKILL_INVENTORY_2026-05-15.json`

## Inventory Snapshot

掃描範圍：

| Root | Count | Role |
|---|---:|---|
| `/Users/jameschen/.agents/skills` | 1408 | 最大混合池，含正式 skill、gstack 鏡像、candidate inbox |
| `/Users/jameschen/Workspace/hermes-agent/skills` | 87 | Hermes 正式 taxonomy，可作 reference catalog |
| `/Users/jameschen/.claude/skills` | 46 | Claude/gstack active mirror |
| `/Users/jameschen/Workspace/nexus/.agents/skills` | 19 | Nexus repo-local curated skills |
| `/Users/jameschen/.openclaw/skills` | 2 | OpenClaw local skills |
| `/Users/jameschen/.codex/vendor_imports/skills/skills` | 38 | Codex imported vendor skills |
| `/Users/jameschen/.codex/plugins/cache` | 11 | Codex plugin-contributed skills |
| `/Users/jameschen/.codex/worktrees` | 136 | Worktree copies, not canonical |
| `/Users/jameschen/.codex/skills_OLD` | 6 | Archive |
| `/Users/jameschen/.codex/skills.bak.20260512111536` | 6 | Archive |
| `/Users/jameschen/.antigravity/skills` | 0 | Root exists, no `SKILL.md` found |
| `/Users/jameschen/.gemini/skills` | 0 | Root exists, no `SKILL.md` found |

Totals:

- Total `SKILL.md`: 1759
- Active-root files: 1562
- Vendor files: 49
- Worktree copies: 136
- Archive files: 12
- Candidate inbox files: 574
- Autogen files: 21
- Duplicate skill names: 114

## Immediate Findings

1. `.agents/skills` is not a clean production catalog.
   It mixes curated skills, gstack mirrors, generated candidates, and runtime-specific copies.

2. Candidate skills must be quarantined from Nexus routing.
   The `candidate-skill-from-*` family has 574 entries. These are useful as raw material, but too noisy and too expensive for direct runtime exposure.

3. Nexus repo-local skills are the safest current mount set.
   `/Users/jameschen/Workspace/nexus/.agents/skills` has 19 skills and already matches the project domain.

4. Hermes skills are useful as reference modules, not direct Nexus mounts.
   Hermes has a well-shaped taxonomy across research, software development, GitHub, MLOps, documents, creative, Apple/productivity, and agent runtimes.

5. Codex plugin/vendor skills should stay read-only and provider-scoped.
   They are runtime capabilities, not Nexus product policy.

6. Antigravity and Gemini skill roots currently do not contain `SKILL.md`.
   They should remain tracked as roots, but not considered active skill sources until files appear.

## Canonical Source Policy

| Tier | Meaning | Roots |
|---|---|---|
| `nexus_curated` | Skills Nexus may mount directly | `/Users/jameschen/Workspace/nexus/.agents/skills` |
| `external_reference` | Read for design, copy only after review | `/Users/jameschen/Workspace/hermes-agent/skills`, selected `.agents/skills` |
| `runtime_vendor` | Available through current agent runtime, not Nexus policy | `.codex/vendor_imports`, `.codex/plugins/cache` |
| `provider_mirror` | Runtime mirror, not canonical | `.claude/skills`, `.openclaw/skills` |
| `candidate_inbox` | Raw candidate material, never auto-load | `candidate-skill-from-*`, `auto-gen-*` |
| `archive` | Do not load, only historical reference | `skills_OLD`, `skills.bak`, archived roots |
| `worktree_copy` | Ignore for canonical decisions | `.codex/worktrees/**/SKILL.md` |

## Capability-Skill Mount Contract

Each mounted skill needs:

- `capability`: stable Nexus capability domain.
- `load_when`: task condition, written as route trigger semantics.
- `do_not_load_when`: negative trigger.
- `cost_tier`: `light`, `medium`, or `heavy`.
- `evidence_required`: route reason, skill id, evidence refs, and outcome contribution.
- `replacement_rule`: when to rewrite, split, demote, or retire.

## Proposed Nexus Capability Mounts

### Benchmark And Promotion

Primary Nexus skills:

- `nexus-benchmark-continuous-optimization`
- `nexus-benchmark-public-report`
- `nexus-goal-closure-executor`

Load when:

- Running public/commercial benchmark lanes.
- Comparing same-model direct vs Nexus arms.
- Producing promotion, x1/x3, public claim, route evidence, cost ledger, or trust gate reports.

Do not load when:

- The task is ordinary coding without benchmark/promotion claims.
- The user only asks for a quick local code explanation.

Evidence required:

- benchmark taskset hash
- model/provider contract
- route evidence contract status
- public claim gate status
- cost and trust gate status

### Governance And Trust

Primary Nexus skills:

- `nexus-root-cause-probe`
- `diagnose`
- `acceptance-evidence-failclosed` from external reference

Load when:

- Claim/evidence mismatch is possible.
- Public gate, trust mismatch, missing evidence, hidden verifier, or replayability is involved.
- A run returns PASS but user questions whether it is truly complete.

Do not load when:

- The output is explicitly exploratory and not a claim.

Evidence required:

- mismatch taxonomy
- detector hit or absence
- evidence refs
- fail-closed verdict

### Repair And Coding

Primary Nexus skills:

- `tdd`
- `diagnose`
- `improve-codebase-architecture`

Reference skills:

- Hermes `test-driven-development`
- Hermes `systematic-debugging`

Load when:

- Fixing bugs, adding tests, refactoring a local module, or reducing coupled code.
- Hidden verifier or regression risk exists.

Do not load when:

- The task is a pure report/summary.
- The code path is read-only analysis.

Evidence required:

- changed files
- targeted tests
- reason for test scope
- regression risk

### Research And Source Discipline

Primary Nexus skills:

- `grill-with-docs`
- `zoom-out`

Reference skills:

- Hermes `arxiv`
- Hermes `research-paper-writing`
- `.agents/skills/gbrain-academic-verify`

Load when:

- User provides papers, external research methods, or asks whether a concept should influence Nexus.
- The answer needs source discipline and direct mapping into Nexus contracts.

Do not load when:

- The user asks for an implementation task that can be solved from local code.

Evidence required:

- source/path/ref used
- how it maps to Nexus capability or gate
- what not to adopt

### Planning And Handoff

Primary Nexus skills:

- `to-prd`
- `to-issues`
- `triage`
- `grill-me`

Load when:

- User asks for long plan, implementation slicing, issue breakdown, or next-agent handoff.

Do not load when:

- The task is already an executable code change with clear scope.

Evidence required:

- objective
- scope
- blocked assumptions
- continuation steps

### Notebook And Knowledge Injection

Primary Nexus skills:

- `notebooklm-bulk-injector`
- `notebooklm-context-bridge`

Load when:

- User asks to bridge, inject, or extract from NotebookLM-style knowledge sources.

Do not load when:

- The task is standard local repo analysis.

Evidence required:

- source notebook/context
- extraction boundary
- no-hallucination statement

## Quarantine Rules

Never auto-load:

- `candidate-skill-from-*`
- `auto-gen-*`
- `.codex/worktrees/**`
- `skills_OLD`
- `skills.bak.*`
- runtime plugin skills unless current runtime explicitly exposes them

Promote a candidate only after:

1. Description rewritten as `Load when...`.
2. Negative triggers added.
3. Eval prompts created.
4. One with-skill vs baseline comparison run.
5. Evidence that it improves verified delivery, trust, cost, or route precision.

## Replacement Rules

| Signal | Meaning | Action |
|---|---|---|
| Skill often loads off-target | Description is too broad | Rewrite trigger and add negative eval |
| Skill often missed when needed | Description lacks task language | Add real query phrases and positive eval |
| Skill does not improve verified delivery | Context tax not justified | Demote or retire |
| Skill only repeats global prompt | No unique leverage | Merge into capability policy or delete |
| Skill body keeps growing | Too many branches | Split references/subskills |
| Skill requires fresh external facts | High drift risk | Replace with tool lookup pattern |
| Skill creates evidence but no outcome contribution | Decorative evidence | Remove from promotion path |

## Next Implementation Slices

1. Add a lightweight `skill_catalog` artifact for Nexus route policy.
   It should read this inventory JSON and output only curated `nexus_curated` entries plus explicit approved external references.

2. Add `skill_mount_contract` to benchmark evidence rows.
   Fields: `capability`, `skill_id`, `load_reason_codes`, `evidence_refs`, `outcome_contributed`.

3. Add negative route tests.
   Ensure candidate/autogen/archive/worktree skills cannot be mounted in public benchmark lanes.

4. Run Flash 50 skill-routing validation.
   Validate delivery, trust=0, route evidence, expected capability evidence, and no cost regression.

5. Run Flash 100/150 after skill routing stabilizes.
   This becomes route/skill overfit validation, not direct baseline promotion.

