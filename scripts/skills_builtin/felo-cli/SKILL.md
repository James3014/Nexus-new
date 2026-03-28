# felo-cli (builtin stub)

## Purpose
Provide optional research retrieval bridge for Phase X/D.

## Minimum Protocol
1. Query scope and hypothesis.
2. Collect evidence snippets.
3. Return source-indexed summary.


## Trigger Precision
- Match only when task scope clearly maps to this skill.
- Reject ambiguous prompts and request routing fallback.


## Output Contract
- Must return actionable result.
- Must include failure reason when no action can be applied.
- Must avoid claiming success without verifiable evidence.
