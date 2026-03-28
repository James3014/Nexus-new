# codebase_investigator (builtin stub)

## Purpose
Provide a deterministic diagnostic baseline for Phase D.

## Minimum Protocol
1. Capture repro symptoms.
2. Narrow likely file/symbol scope.
3. Propose root-cause candidates with confidence.
4. Output next actionable repair step.

## Output Contract
- `diagnosis.summary`
- `diagnosis.root_causes[]`
- `diagnosis.next_action`
