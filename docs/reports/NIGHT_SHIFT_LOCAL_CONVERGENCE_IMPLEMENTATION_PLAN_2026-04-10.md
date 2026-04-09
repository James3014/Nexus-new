# Implementation Plan: Night Shift Local Convergence With Nexus Battlesuit + Gemini CLI OAuth

## Goal
Turn `scripts/nightshift.py` from a mock optimization loop into a local autonomous runner that:

- continuously iterates on a real target file,
- stops when the target reaches convergence,
- automatically switches to the next pending target,
- and leaves behind real code changes inside an isolated Nexus worktree.

## Non-Goals
- No direct Gemini HTTP API integration in this phase.
- No codebase-wide autonomous harvest back into the main worktree in this phase.
- No semantic alias resolver for fuzzy task names like `cors`; this phase supports explicit file-path targets first.

## Architecture

### Control Plane
- `scripts/nightshift.py`
  - owns the task queue
  - owns convergence tracking
  - owns worktree lifecycle
  - owns validation and rollback decisions

### Battlesuit Layer
- `nexus/services/gateway.py`
  - remains the only Night Shift path that talks to Gemini CLI
  - wraps OAuth CLI invocation
  - exposes a generic structured-JSON request path for Night Shift

### Execution Backend
- `gemini` CLI
  - runs headless
  - receives prompt + source code
  - returns structured JSON that contains a whole-file candidate

## Vertical Slice Scope

### 1. Target Resolution
- Add a target resolver in `scripts/nightshift.py`.
- Resolution priority:
  1. explicit `--target_file`
  2. path-like task entries from `--tasks`
  3. fallback from `program.md` target line
- Phase-1 support guarantees correct behavior for repo-relative file paths like `scripts/test_repair_dummy.py`.

### 2. Structured Candidate Generation
- Extend `BattlesuitGateway` with a generic structured JSON method.
- Night Shift generation schema:
  - `status`
  - `summary`
  - `target_file`
  - `content`
  - `changed_regions`
- Generation mode is `whole_file`, not free-form fenced code.

### 3. Physical Validation
- Write the generated whole-file candidate into the leased worktree target path.
- Validate before scoring:
  - `python -m py_compile <target>` for Python files
  - if filename suggests a local smoke script (`test_` or `dummy`), run `python <target>`
- Any validation failure becomes a scored failure and triggers rollback.

### 4. LLM-Assisted Scoring Through Battlesuit
- Use the same Gateway path for judging candidate quality.
- Judge schema:
  - `status`
  - `summary`
  - `score`
  - `issues`
- Judge input includes:
  - task id
  - original source
  - candidate source
  - validation result
  - current best score

### 5. Convergence Control
- Add `convergence_patience` to Night Shift.
- Maintain:
  - `best_score`
  - `no_improve_streak`
  - `best_commit`
- Convergence rule:
  - if `no_improve_streak >= convergence_patience`, print convergence message and stop this target early

### 6. Auto Switch To Next Target
- Keep `main()` task list execution sequential for the first reliable version.
- Once one target converges, return from `shift.run()` and let the next task in `task_list` start automatically.
- This preserves the existing worker mental model without rewriting a scheduler.

## CLI Changes

### New / Updated Flags
- `--convergence-patience`
  - default: `5`
- `--target_file`
  - keep for explicit override
- `--tasks`
  - support repo-relative file paths directly

### No Semantic Change
- Keep `--auto-stop` for existing campaign/governance semantics.
- Do not overload `--auto-stop` with per-target convergence logic.

## State Machine

### Round Lifecycle
1. Resolve target file.
2. Read current file contents.
3. Ask Battlesuit Gateway for a structured whole-file candidate.
4. If candidate is empty or invalid, mark round failed.
5. Materialize candidate in worktree.
6. Run validation commands.
7. If validation fails, assign score `0.0`, rollback, increment `no_improve_streak`.
8. If validation passes, ask Battlesuit Gateway to score candidate.
9. If score beats `best_score`, commit and reset streak.
10. If score does not beat `best_score`, rollback and increment streak.
11. If streak reaches patience, declare convergence and exit current target.

## Acceptance Criteria

### Functional
- Night Shift can accept `--tasks "scripts/test_repair_dummy.py"`.
- Night Shift generates real candidate content through Nexus Battlesuit + Gemini CLI OAuth.
- Night Shift writes the candidate into the leased worktree target path.
- Night Shift exits early on convergence instead of always running `max_rounds`.
- Night Shift automatically proceeds to the next target in `task_list`.

### Safety
- Candidate validation happens before commit.
- Invalid Python output never becomes the best committed state.
- Rollback uses the current best commit, not the last attempted candidate.

### Observability
- Trace log records improved vs rollback vs convergence outcomes.
- Final output clearly states target path and best score.

## Verification Plan

### Automated
- Add focused tests for:
  - target resolver behavior
  - convergence streak stopping
  - candidate generation path with fake gateway output
  - validation failure rollback behavior

### Local Smoke
- Run Night Shift against `scripts/test_repair_dummy.py` with a fake or patched gateway in tests.
- If local OAuth credentials are available, run a manual smoke using Gemini CLI.

## Known Risks

### Risk: Gemini CLI output shape drifts
- Mitigation: keep Gateway JSON parsing tolerant and confined to one file.

### Risk: Model returns partial code instead of whole file
- Mitigation: whole-file schema contract plus validation gate.

### Risk: Autonomous loop modifies the wrong file
- Mitigation: explicit target resolution and path logging before each round.

## Files Planned
- `docs/reports/NIGHT_SHIFT_LOCAL_CONVERGENCE_IMPLEMENTATION_PLAN_2026-04-10.md`
- `nexus/services/gateway.py`
- `scripts/nightshift.py`
- `tests/test_nightshift_local_convergence.py`

## Completion Checkpoint
- The feature is complete when a local run can iterate on a real file through Nexus Battlesuit, stop on convergence, and continue to the next target without human intervention.
