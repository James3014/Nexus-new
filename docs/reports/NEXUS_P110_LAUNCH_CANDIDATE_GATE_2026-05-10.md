# Nexus P110 Launch Candidate Gate

Date: 2026-05-10

## Target

Gemini 3 Flash and Gemini 3.1 Pro wearing Nexus should approach GPT-5.5 direct on fixed public tasks while preserving trust safety, Nexus learning closure, route-cost discipline, and public-claim evidence.

## Result

P110 produced a launch-candidate gate instead of another partial benchmark report.

Current status:

- Quality ready: yes.
- Launch ready: no.
- CLI behavior: exits non-zero when `launch_ready=false`.

The blocker is not a failing Nexus quality result. The blocker is that the GPT-5.5 direct teacher reference currently has 4 fixed tasks, while the launch target requires 8-12 fixed public tasks.

## Data

| Check | Result |
|---|---|
| GPT-5.5 direct teacher verified rate | 0.75 |
| Flash + Nexus overlap verified rate | 1.00 |
| Pro + Nexus overlap verified rate | 1.00 |
| Flash trust mismatch | 0 |
| Pro trust mismatch | 0 |
| Flash public claim gate | PASS |
| Pro public claim gate | PASS |
| Flash wall ratio | 1.6048 |
| Pro wall ratio | 1.8078 |
| Flash token ratio | 1.1098 |
| Pro token ratio | 1.1285 |
| Pre-Flash deterministic gate | PASS |
| P110 quality_ready | true |
| P110 launch_ready | false |
| P110 CLI launch blocker | active |

## Why Earlier Loops Kept Stopping

The loop kept stopping because prior gates answered narrower questions:

- same-model A/B passed
- pre-flash gates passed
- teacher-overlap quality passed

Those were useful, but none of them encoded the full final target. P110 fixes that by separating:

- quality readiness
- launch readiness
- cost warnings
- teacher-reference breadth blockers

This prevents a local PASS from being mistaken for full objective completion.

The reason the loop cannot honestly claim full target completion at P110 is concrete: the teacher-reference suite is still 4 tasks, not the required 8-12 tasks. Running more Flash/Pro on the same 4-task slice would not close that blocker; it would only repeat a quality-ready result.

## Evidence

- P110 gate output: `.nexus/reports/p110_launch_candidate_gate.json`
- P90 teacher gate: `.nexus/reports/p90_teacher_reference_gate.json`
- Flash gap matrix: `.nexus/reports/p76_p90_flash_vs_gpt55_direct_gap.md`
- Pro gap matrix: `.nexus/reports/p76_p90_pro_vs_gpt55_direct_gap.md`
- P110 gate script: `scripts/ops/nexus_p110_launch_candidate_gate.py`
- P110 gate tests: `tests/ops/test_nexus_p110_launch_candidate_gate.py`

## Verification

```bash
uv run pytest -q tests/ops/test_nexus_p110_launch_candidate_gate.py tests/benchmark/test_teacher_reference_gate.py
uv run python scripts/ops/nexus_p110_launch_candidate_gate.py --teacher-run .nexus/reports/p231_p240_codex55_direct_teacher_4task --teacher-arm without_nexus --student flash_p72=.nexus/reports/flash_8x2_p72_policy_preflight --student pro_p73=.nexus/reports/pro_8x1_p73_policy_preflight --output .nexus/reports/p110_launch_candidate_gate.json
```

Observed:

- 5 tests passed.
- P110 gate generated.
- `quality_ready=true`.
- `launch_ready=false`.
- CLI returns non-zero for launch-blocked state.

## Next Goal

Reach full launch readiness, not just quality readiness.

Completion criteria:

- GPT-5.5 direct teacher suite expanded to at least 8 fixed public tasks.
- Flash + Nexus and Pro + Nexus each stay at >= 90% of GPT-5.5 direct verified rate.
- Trust mismatch remains 0.
- Pro aggregate wall warning is removed or justified by lane-level verified-success ROI.
- Public report can truthfully claim same-model verified lift and teacher-reference proximity.

## Next Long Plan

P111: Build the 8-12 task GPT-5.5 direct teacher suite from existing public benchmark cases without task-id-specific route policy.

P112: Run or ingest GPT-5.5 direct teacher rows for the expanded suite.

P113: Re-run Flash + Nexus and Pro + Nexus only on the expanded fixed suite.

P114: If any task fails, inspect trace first and patch route/context policy before continuing.

P115: Remove the Pro aggregate wall warning by lane-specific context/phase slimming, not by lowering governance gates.

P116: Regenerate Autodata / S2T / Agent-Lightning-style training rows from the verified expanded suite.

P117: Re-run P110 gate with `target_teacher_tasks >= 8`.

P118: If `quality_ready=true` but `launch_ready=false`, fix the exact blocker and re-run.

P119: Produce public report with limitation section.

P120: Commit coherent runtime, test, report, and learning-closure artifacts.
