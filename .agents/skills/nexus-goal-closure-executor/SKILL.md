---
name: nexus-goal-closure-executor
description: Use when a Nexus task must be driven from a declared final goal through a long plan, dynamic replanning, failure triage, implementation, testing, and evidence-backed closure without stopping at incomplete phase labels. Especially useful when the user asks to "execute until the goal is complete", "do not stop until validation", "self-adjust the plan", "run to P/N/phase X only if each item is actually done", or complains that prior plans stopped before the target was achieved.
metadata:
  short-description: Execute Nexus goal plans to evidence-backed closure
---

# Nexus Goal Closure Executor

Use this skill when the user wants a goal-driven execution loop, not a short plan or partial phase report.

## Core Contract

The plan is valid only if it has a final target state and a verifiable closure gate.

Do not report "P120 complete" or "phase done" unless all promised work for that phase exists in code/docs/tests/reports and passed the relevant checks. A phase number is not progress by itself.

## Required Output Shape

Follow the repo style when reporting:

```text
[任務] -> ...
[數據] -> ...
[證據] -> ...
```

Keep the report compact. Include modified files, verification commands, key outputs, and residual debt.

## Workflow

1. Restate the final goal as an acceptance gate.
   - Include what must improve, what must not regress, and what evidence proves it.
   - If the user gives a phase target, treat it as a milestone, not the real goal.
   - If the phase target conflicts with the real goal, prioritize the real goal and say so.

2. Inventory the current state before editing.
   - Check branch and dirty files.
   - Identify user-owned dirty files and avoid reverting them.
   - Read only the files required to understand the relevant subsystem.
   - Prefer `rg`, targeted `sed`, and existing tests over broad file dumps.

3. Build a long plan with closure gates.
   - Each item must have a concrete deliverable.
   - Each item must have a verification method.
   - Include a "stop condition" only for true blockers: missing credentials, destructive action, external service unavailable, or user decision required.
   - Do not include vague items like "continue improving" without a measurable gate.

4. Execute in loops.
   - Implement the smallest coherent slice.
   - Run the narrowest relevant test.
   - If it fails, diagnose, patch, and rerun without asking unless the fix is destructive or changes product direction.
   - Update the plan internally when evidence contradicts the original route.
   - Continue until the final acceptance gate is met or a true blocker is reached.

5. Treat failures as data.
   - For every meaningful failure, capture cause, fix, and prevention.
   - If the repo requires learning writeback, write the lesson to the relevant Learning Closure Matrix, ADR, or report before finalizing.
   - Do not hide failing benchmark rows; classify them as product issue, benchmark issue, provider issue, or environment issue.

6. Validate against the real target.
   - Run unit tests for touched modules.
   - Run integration/smoke tests for changed runtime paths.
   - For Nexus route/cost/benchmark work, include same-model bare vs Nexus evidence when available.
   - Do not claim public improvement without stable denominator, raw evidence path, and limitation scope.

7. Close with evidence.
   - List exact files changed.
   - List commands and key results.
   - State whether the final goal is met.
   - State residual debt only if it is outside the accepted closure gate.

## Dynamic Replan Rules

Use these rules instead of stopping for routine issues:

- Test failure: inspect traceback or report row, patch likely cause, rerun narrow test.
- Benchmark fail: read trace/log/result first; do not repeatedly rerun without diagnosis.
- Cost regression: split by route selection, phase wall time, prompt payload, provider calls, and verification overhead.
- Trust regression: preserve fail-closed safety first; reduce cost by slimming payload or route materialization, not by removing evidence gates blindly.
- Dirty worktree: isolate own changes; do not revert unrelated user changes.
- File-count pressure: commit or summarize only if user asked or repository policy requires it; otherwise keep changes focused.
- External model/service unavailable: produce deterministic local validation and mark provider validation blocked.

## Nexus-Specific Checks

For Nexus route, learning, S2T, benchmark, or cost work, verify the relevant subset:

- `uv run pytest ...` for touched modules.
- `uv run python scripts/ops/capability_route_smoke.py --print-only` or full smoke when route payload changes.
- Same-model A/B when public benchmark claims are involved.
- `trust_mismatch == 0` for launch/gate claims unless the user explicitly accepts a research-only experiment.
- Evidence paths under `.nexus/reports/`, docs/reports, or generated benchmark result files.
- Learning/training writeback if the task touches learning closure, S2T traces, Autodata, Agent Lightning export, or promoted route policy.

## Anti-Patterns

Avoid these:

- Reporting a phase number as complete when its deliverables were not implemented.
- Replanning forever without executing.
- Running expensive Flash/Pro benchmarks before local smoke and deterministic tests.
- Treating Nexus as an agent that directly solves tasks; Nexus is the control/runtime layer that models wear.
- Optimizing benchmark-specific prompts or fixtures instead of routing, evidence, and cost policy.
- Removing governance gates just to reduce cost.
- Creating broad rewrites when a seam-level fix is sufficient.

## Final Report Template

```text
[任務] -> <final goal and whether it is met>

[數據] ->
- Goal gate: <pass/fail>
- Quality: <key metrics>
- Cost: <key metrics>
- Safety: <trust/evidence status>
- Residual debt: <none or explicit scoped items>

[證據] ->
- Files: <changed files>
- Commands: <commands and key outputs>
- Reports: <paths>
```
