# Campaign Index: Agent Skills Lifecycle Convergence

artifact_authority: current
owner: James Chen
status: active, machine-local and commit-forbidden
AUTO_CHAIN: false

## Objective

Align the seven machine-local Nexus Skills with the frozen Lifecycle V1
contract without changing Nexus runtime authority or adding a second router.

## Authority boundaries

- Source of truth remains `/Users/jameschen/Workspace/nexus` and its current
  `AGENTS.md`, Task Cards, Gateway manifest, and lifecycle receipts.
- Skill files are ChatGPT-side operating instructions, not runtime code.
- No external Skill file may grant approval, integration, push, cleanup, or
  production/public claim authority.
- `commit_forbidden: true`: edits under `/Users/jameschen/.agents/skills` are
  machine-local configuration and must not enter a Nexus Git commit.

## Active card

`00-lifecycle-contract-overlay.md`

## Exit gate

- All seven named Skills contain the same lifecycle identity vocabulary:
  Task/Attempt/Action, definition hashes, reconnect reconciliation,
  uncertain mutation, and one exact next action.
- No Skill introduces `nexus-lifecycle-controller`, a new router, or broad
  shell authority.
- Changed external files are limited to the seven allowed Skill files.
- A fresh grep-based consistency check passes; Nexus Git worktree remains
  unchanged except for this governance card.
