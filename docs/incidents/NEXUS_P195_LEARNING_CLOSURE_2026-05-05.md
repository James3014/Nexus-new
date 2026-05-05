# P195 Learning Closure

## Failure 1: Report Alias Drift
- Symptom: report test expected Brain Hub Manifest section but it was absent.
- Root cause: renderer looked for `brain_hub_manifest`, while the planned row shape used `brain_hub_guidance.manifest`.
- Lesson: report evidence helpers must support the row producer's nested payload names, not only new top-level names.
- Closure: `_brain_hub_payload()` now supports `brain_hub_guidance.manifest` and top-level aliases.

## Failure 2: Ordered Phase Evidence Regressed Existing Helper
- Symptom: changing phase aggregation from set to list caused `.update()` runtime errors.
- Root cause: local change preserved phase order but missed existing set API calls.
- Lesson: when changing collection semantics for report readability, tests must cover old helpers and new sections together.
- Closure: phase aggregation now uses append-if-missing in both guidance and evidence helpers; report test suite passed.

## Failure 3: Indentation Regression During Fast Patch
- Symptom: pytest collection failed with `IndentationError`.
- Root cause: single-line indentation was lost while editing inside an `if` block.
- Lesson: after patching Python control blocks, immediately run the smallest import/pytest target before broader suites.
- Closure: indentation fixed and benchmark report tests passed.
