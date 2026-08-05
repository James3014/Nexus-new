---
artifact_authority: current
owner: James Chen
status: active
purpose: Conditional execution contract for governed Nexus task cards.
---

# Task Execution Contract

This is the L1 contract loaded for a governed mutating task. The active
Git-tracked Task Card remains the task-specific authority; this document
supplies the shared schema and gates. It is not required for an eligible
Owner-authorized `DIRECT_CANONICAL` change.

## Direct canonical boundary

An explicit current Owner request may authorize the primary agent to make one
bounded change directly in the canonical checkout without a Task Card or
lifecycle state. The agent freezes the request-derived file scope, preserves
unrelated dirty state, runs relevant checks plus `git diff --check`, and reports
the exact changed files and evidence.

Escalate to this governed contract before mutation when implementation is
delegated, requires an isolated Target, crosses subsystems, changes
route/lifecycle/workforce authority, weakens security, changes a migration or
schema, performs cleanup or protected-branch/ref operations, creates a
Candidate, or supports a production/public claim. Direct work does not commit,
push, merge, delete, or auto-chain without exact Owner authority.

## Governed discovery and authority

1. Anchor at the canonical root and verify root, branch, status, and worktrees.
2. Read `AGENTS.md`, the campaign `INDEX.md`, and only the current frontier card.
3. Verify the lifecycle task id, card path, and card hash before editing.
4. Runtime `.nexus` state may record receipts and hashes but cannot replace or
   rewrite the card. `AUTO_CHAIN=false` unless the index explicitly enables it.

Every active card declares objective, authority/status, inputs, dependencies,
allowed files, forbidden scope, verification commands, required evidence, exit
criteria, residual-debt handling, and block classification. Its allowed and
forbidden paths, file-count ceiling, and commit policy are the operative scope.

## Mutation safety

- Preserve unrelated dirty state. Use a clean governed Target for isolation;
  never reset, stash, clean, overwrite, or absorb ambiguous changes.
- Do not hand-edit lifecycle JSON or protected control-plane state. Use formal
  API, CLI, or service surfaces and preserve receipts.
- A worker may not approve, integrate, push, delete refs, or clean up its own
  Candidate unless the card grants that exact authority.

## Commit and Candidate gates

Implementation cards require a scoped commit unless explicitly read-only,
audit-only, or commit-forbidden. Before committing:

- verify only allowed files changed;
- run the card's exact verification commands and `git diff --check`;
- inspect tracked and staged deletions, both diff stats, and the full staged diff;
- create the commit with the exact card scope and report its SHA.

Candidate formation binds the verified commit SHA and task-card hash to the
receipt. Candidate, approval, integration, push, cleanup, and production/public
claims are separate lifecycle states. A failed required commit is a block, not
completion.

## Blocks and residual debt

`RECOVERABLE_BLOCK` preserves the same card for retry after an external or
environmental condition. `HARD_BLOCK` stops mutation for authority, safety,
architecture, evidence-integrity, irreversible-risk, or specification conflict.
Neither block permits promotion, cleanup, or downstream activation. Supersede a
card only with an explicit `superseded_by` link and a new independently hashed
card.
