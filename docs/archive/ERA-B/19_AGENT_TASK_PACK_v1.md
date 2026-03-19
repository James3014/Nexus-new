# Agent Task Pack v1 (Direct-Use)

## Goal

Implement the next internal slice of the **new Nexus runtime** using the current upgraded Nexus base.

This task pack is designed to be pasted directly to another agent.

## Execution Mode (Mandatory)

Implementation must run through the **current Nexus system**, not an ad-hoc standalone workflow.

Required runtime loop:

```text
Gemini edits
  -> milestone scripts/codex-loop.sh review
    -> /tmp/codex_next_action.json
      -> scripts/core/gemini_handoff.py prompt
        -> Gemini next round
```

At minimum, each milestone must execute:

```bash
scripts/codex-loop.sh --mode audit <files...> --emit-gemini-handoff
```

Do not bypass Nexus gate/review when implementing this task pack.

## Quota-Aware Gate Policy (Mandatory)

Given limited Codex quota, use milestone gates instead of per-edit gates.

Rules:

1. Max Codex gates per slice: `2` during implementation + `1` final pre-commit gate.
2. Do not run Codex gate after every small edit.
3. Trigger a gate only when one of these is true:
   - a test set turns from red to green
   - a module boundary is completed
   - before commit
4. If two gates fail with the same failure signature:
   - follow `next_action` from `/tmp/codex_next_action.json`
   - continue Gemini repairs without immediate extra Codex gate
   - run next gate only at the next milestone
5. Reserve at least one final gate for merge/commit quality.

## Preflight Safety (Mandatory)

Do not edit the active working copy directly.

Run these steps before implementation:

1. Create an isolated branch:

```bash
git switch -c feat/nexus-1.5.2-<agent>-<date>
```

2. Freeze baseline for rollback/audit:

```bash
git tag -f nexus-pre-1.5.2-baseline-<date>
git rev-parse HEAD
```

3. Optional but recommended: use a separate worktree:

```bash
git worktree add ../Muse-Nexus-1.5.2 feat/nexus-1.5.2-<agent>-<date>
```

Only start code changes after these steps are completed.

## Read First (Strict Order)

1. `docs/00_PROJECT_INDEX.md`
2. `docs/12_AGENT_EXECUTION_GUIDE.md`
3. `docs/17_GEMINI_CODEX_HANDOFF_USAGE.md`
4. `docs/18_REFACTOR_PROGRESS_BOARD.md`
5. `docs/11_FIRST_CUT_FILE_PLAN.md`
6. `docs/13_ACCEPTANCE_CHECKLIST.md`

## Scope (Allowed)

Only touch files required for this slice. Prefer additive changes.

Primary targets:

- `scripts/core/state_contracts.py` (create if missing)
- `scripts/core/state_io.py` (create if missing)
- `scripts/core/context_hub.py` (create if missing)
- `scripts/core/skills_router.py` (create if missing)
- `scripts/codex_loop_brain.py` (minimal integration only)
- `scripts/drclaw_diagnosis.py` (minimal integration only)

## Scope (Forbidden)

- No large repo restructuring.
- No unrelated dashboard/memory engine refactor.
- No TOON in state contracts.
- No broad rewrite of `codex_loop_brain.py`.
- No destructive git operations.

## Runtime Contract Rules

1. JSON/JSONL is the only authority format.
2. Reads must be compatibility-safe for missing keys.
3. New fields must be additive.
4. Side effects must be explicit and minimal.

## Implementation Strategy (Small Steps)

1. Create/extend contracts and defaults.
2. Add state read/write helpers.
3. Add context_hub skeleton for D/R/A packs.
4. Add skills_router skeleton with explainable output:
   - `reason`
   - `score`
   - `threshold`
5. Integrate minimally into repair/diag entry points.

## Required Tests (TDD)

At minimum add/update tests for:

- contract default loading
- legacy missing-key fallback
- context pack assembly shape
- router decision determinism for sample metadata

Run:

```bash
python3 -m pytest -q
```

If full suite is too broad, run targeted tests and report exactly what was run.

## Required Runtime Checks

1. Smoke check imports for touched modules.
2. Verify one end-to-end internal path does not crash.
3. Verify `codex_next_action` and handoff flow still works.

## Handoff Commands (Current Runtime)

```bash
scripts/codex-loop.sh --mode audit <files...> --emit-gemini-handoff
scripts/codex-loop.sh --handoff-only --emit-gemini-handoff --handoff-output /tmp/gemini_task.txt
```

## Output Format (Must Follow)

Report in this exact structure:

1. `Changed Files`
2. `What Implemented`
3. `What Not Implemented`
4. `Tests/Checks Run`
5. `Residual Risks`

## Definition of Done

- Code compiles/imports.
- TDD coverage exists for new logic.
- No unrelated files changed.
- Acceptance checklist items for this slice are satisfied.
- Changes are small, modular, and decoupled.
