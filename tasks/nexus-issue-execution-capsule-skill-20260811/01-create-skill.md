---
task_id: nexus-issue-execution-capsule-skill-20260811-01
campaign_id: nexus-issue-execution-capsule-skill-20260811
status: in_progress
authority: governed delegated worker
owner: James Chen
baseline: 374348c89e7814e11d55e00ea397dc5a6effe471
setup_commit_required: true
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

## Exit criteria and evidence

- Setup commit exists before skill mutation.
- `SKILL.md` and `agents/openai.yaml` exist and no other skill resources exist.
- Validator passes and `git diff --check` passes.
- Staged and unstaged scope audits show only allowed files.
- Skill commit exists and is bound to this card's hash.

## Block classification

Use `RECOVERABLE_BLOCK` for tool/environment failures that can be retried.
Use `HARD_BLOCK` for authority, scope, specification, or evidence-integrity
conflicts. Never widen scope to resolve a block.
