# git-manager (builtin stub)

## Purpose
Baseline git workflow for planning/closeout phases.

## Minimum Protocol
1. Inspect branch and working tree state.
2. Stage only task-scoped files.
3. Commit with explicit intent.
4. Preserve unrelated local edits.

## Guardrails
- No destructive reset unless explicitly requested.


## Trigger Precision
- Match only when task scope clearly maps to this skill.
- Reject ambiguous prompts and request routing fallback.


## Output Contract
- Must return actionable result.
- Must include failure reason when no action can be applied.
- Must avoid claiming success without verifiable evidence.
