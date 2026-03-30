# skill-creator-advanced (builtin stub)

## Purpose
Create or refactor skills with trigger quality checks.

## Minimum Protocol
1. Define trigger and non-trigger examples.
2. Define output contract and constraints.
3. Add lightweight validation checklist.
4. Record expected activation scope.


## Trigger Precision
- Match only when task scope clearly maps to this skill.
- Reject ambiguous prompts and request routing fallback.


## Output Contract
- Must return actionable result.
- Must include failure reason when no action can be applied.
- Must avoid claiming success without verifiable evidence.
