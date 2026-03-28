# self-healer (builtin stub)

## Purpose
Provide a safe auto-repair baseline for Phase R.

## Minimum Protocol
1. Run check and capture failure evidence.
2. Apply minimal scoped fix.
3. Re-run validation.
4. Stop on unresolved risk and escalate.

## Safety
- Never claim success without verification output.
- Keep modifications scoped to task-relevant files.


## Trigger Precision
- Match only when task scope clearly maps to this skill.
- Reject ambiguous prompts and request routing fallback.


## Output Contract
- Must return actionable result.
- Must include failure reason when no action can be applied.
- Must avoid claiming success without verifiable evidence.
