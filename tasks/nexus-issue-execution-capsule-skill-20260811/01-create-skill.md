---
task_id: nexus-issue-execution-capsule-skill-20260811-01
campaign_id: nexus-issue-execution-capsule-skill-20260811
status: COMPLETE
authority: governed delegated worker
owner: James Chen
baseline: 752d1dec0517b29e1e1179827919e45dac33d131
historical_baseline: 752d1dec0517b29e1e1179827919e45dac33d131
merge_base: 752d1dec0517b29e1e1179827919e45dac33d131
reconciled_main: cdf2570ede5ae218f36f886b696c8da45458043a
current_main: cdf2570ede5ae218f36f886b696c8da45458043a
block_class: NONE
frontier: TERMINAL_RECONCILIATION
frontier_status: COMPLETE
terminal_marker: NEXUS_ISSUE_EXECUTION_CAPSULE_SKILL_PROVEN
claim_ceiling: NEXUS_ISSUE_EXECUTION_CAPSULE_SKILL_ONLY
AUTO_CHAIN: false
---

# Create Nexus Issue Execution Capsule Skill

## Objective

Create a concise repo-local `nexus-issue-execution-capsule` skill using the
skill-creator initializer. It must guide Nexus GitHub Issue/PR/CI repair or
implementation where repeated exploration, environment drift, or sibling
call-site failures are risks.

## Inputs and dependencies

- Root `AGENTS.md`.
- `docs/agents/TASK_EXECUTION_CONTRACT.md`.
- `/Users/jameschen/.mirasim/skills/.system/skill-creator/SKILL.md`.
- `/Users/jameschen/.mirasim/skills/.system/skill-creator/references/openai_yaml.md`.
- Initializer and validator under `/Users/jameschen/.mirasim/skills/.system/skill-creator/scripts/`.

## Allowed files

- `tasks/nexus-issue-execution-capsule-skill-20260811/INDEX.md`.
- `tasks/nexus-issue-execution-capsule-skill-20260811/01-create-skill.md`.
- `.agents/skills/nexus-issue-execution-capsule/**` only, limited to the
  initializer's `SKILL.md` and `agents/openai.yaml` outputs.

## Forbidden scope

- Any other repository file, README, scripts, references, assets, or generated
  examples.
- Repository-wide refactors, scope widening, deletion, cleanup, or lifecycle
  JSON edits.
- Reset, stash, clean, rebase, force-push, push, PR, comment, merge, approval,
  promotion, integration, or production claims.

## Required content

Use imperative concise prose. Trigger from the frontmatter description on Nexus
GitHub Issue/PR/CI repair or implementation risks. Encode smallest authoritative
context; an execution capsule containing current main/head, contract watermark,
exact first failure, allowed/forbidden scope, verification, disproven/do-not-
repeat findings, claim ceiling, and next gate; exact-environment reproducer
topology (cwd, shallow/full history, refs, permissions, credentials,
event/workflow/provider); failure delta; a bounded sibling sweep in the same
API/trust seam; two-stage tests; revision-bound evidence freshness; fail-closed
authority gaps; compact receipts; and correctness over speed. Include minimal
capsule and compact receipt templates. Explicitly forbid scope widening and
repository-wide refactoring.

## Verification

Run from the isolated worktree:

```bash
python3 /Users/jameschen/.mirasim/skills/.system/skill-creator/scripts/init_skill.py nexus-issue-execution-capsule --path .agents/skills --interface 'display_name=Nexus Issue Execution Capsule' --interface 'short_description=Bounded Nexus issue repair with fresh evidence' --interface 'default_prompt=Use $nexus-issue-execution-capsule to execute a bounded Nexus issue repair.'
python3 /Users/jameschen/.mirasim/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/nexus-issue-execution-capsule
git diff --check
git status --short
git diff --stat
git diff --cached --stat
git diff --cached
```

The validator must pass. The final skill commit must contain only the two
initializer outputs; the setup commit must contain only this campaign's two
files. Report both SHAs and exact files. Do not create a Candidate or claim
approval, integration, or production readiness.

## Physical evidence and terminal boundary

- Historical card baseline: `752d1dec0517b29e1e1179827919e45dac33d131`.
- PR #138 head: `ec18a8c5be95b61cfe2e5830254e1d57087a638e`.
- PR #138 merge: `c450c75cedbe7679f564d4eaddb7aa351b8aa0ee`.
- Exact scope: the capsule `SKILL.md`, `agents/openai.yaml`, and this card
  plus INDEX.
- Exact-head workflows: Pytest, Pyright, Bandit, Ruff, and Wiki governance
  completed successfully.
- Independent Agy exact-head review recorded with evidence hash
  `cf176160bf9488810b2f37991d391da065d1680a6cc9bdfd8353dfc38e81a562` and no
  filesystem delta.
- Owner receipt: `POST_COMPLETION_RECONCILIATION` on Issue #137.
- Reconciled current main: `cdf2570ede5ae218f36f886b696c8da45458043a`.

`NEXUS_ISSUE_EXECUTION_CAPSULE_SKILL_PROVEN` is limited to the skill descriptor
and source contract. No runtime eligibility, catalog promotion, selector or
workflow change, route, Workforce, Candidate acceptance, approval, integration,
merge, release, or production claim follows. `AUTO_CHAIN=false`.

## Block classification

Use `RECOVERABLE_BLOCK` for tool/environment failures that can be retried.
Use `HARD_BLOCK` for authority, scope, specification, or evidence-integrity
conflicts. Never widen scope to resolve a block.
