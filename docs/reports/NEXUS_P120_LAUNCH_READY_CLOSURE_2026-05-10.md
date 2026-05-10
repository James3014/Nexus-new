# Nexus P120 Launch Ready Closure

Date: 2026-05-10

## Target

Make Gemini 3 Flash and Gemini 3.1 Pro wearing Nexus approach GPT-5.5 direct on fixed public tasks, with trust-safe and cost-disciplined always-on routing.

## Result

P120 reaches launch-ready status for the current 8-task fixed teacher-reference suite.

The earlier P110 blocker was concrete: only 4 GPT-5.5 direct teacher tasks existed. P120 removed that blocker by running the 8-task GPT-5.5 teacher suite, then re-running the launch candidate gate.

## Data

| Metric | Value |
|---|---:|
| GPT-5.5 direct teacher tasks | 8 |
| GPT-5.5 direct verified rate | 0.875 |
| GPT-5.5 + Nexus verified rate | 1.000 |
| Flash + Nexus teacher-overlap verified rate | 1.000 |
| Pro + Nexus teacher-overlap verified rate | 1.000 |
| Flash required rate | 0.7875 |
| Pro required rate | 0.7875 |
| Flash trust mismatch | 0 |
| Pro trust mismatch | 0 |
| Flash public claim gate | PASS |
| Pro public claim gate | PASS |
| P120 quality_ready | true |
| P120 launch_ready | true |

Cost:

| Arm | Wall ratio | Median wall ratio | Token ratio | Gate status |
|---|---:|---:|---:|---|
| Flash + Nexus | 1.6048 | 1.0480 | 1.1098 | PASS |
| Pro + Nexus | 1.8078 | 1.2959 | 1.1285 | PASS with warning |

The Pro aggregate wall ratio is still slightly above the soft target, but median wall and token ratios remain under hard gate thresholds. The remaining action is optimization, not launch blocking.

## Evidence

- P120 launch gate: `.nexus/reports/p120_launch_candidate_gate.json`
- GPT-5.5 8-task teacher run: `.nexus/reports/p111_p120_codex55_direct_teacher_8task/evidence_bundle.json`
- Flash expanded gap matrix: `.nexus/reports/p111_p120_flash_vs_gpt55_direct_gap.md`
- Pro expanded gap matrix: `.nexus/reports/p111_p120_pro_vs_gpt55_direct_gap.md`
- Flash Autodata manifest: `.nexus/reports/autodata/flash_p120_8task_autodata_manifest.json`
- Pro Autodata manifest: `.nexus/reports/autodata/pro_p120_8task_autodata_manifest.json`
- P110/P120 gate script: `scripts/ops/nexus_p110_launch_candidate_gate.py`

## Verification

```bash
uv run pytest -q tests/ops/test_nexus_p110_launch_candidate_gate.py tests/benchmark/test_teacher_reference_gate.py tests/benchmark/test_route_decision_simulator.py tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_route_cost_optimizer.py tests/app/test_research_flow_service.py tests/engine/test_capability_receipt_adapters.py tests/nexus/codeintel/test_dci_locator.py
```

Observed:

- 276 tests passed.

```bash
uv run python scripts/ops/nexus_p110_launch_candidate_gate.py --teacher-run .nexus/reports/p111_p120_codex55_direct_teacher_8task --teacher-arm without_nexus --student flash_p72=.nexus/reports/flash_8x2_p72_policy_preflight --student pro_p73=.nexus/reports/pro_8x1_p73_policy_preflight --output .nexus/reports/p120_launch_candidate_gate.json
```

Observed:

- `quality_ready=true`
- `launch_ready=true`
- `readiness_blockers=[]`

## Why The Previous Loop Should Not Have Stopped

The previous P110 state had enough information to continue automatically: the only blocker was `teacher_reference_suite_below_launch_target`.

Correct dynamic adjustment:

1. Run the expanded GPT-5.5 direct teacher suite.
2. Re-run the launch candidate gate.
3. Only stop if the expanded teacher run fails or if Flash/Pro no longer meet the quality/cost/trust gates.

That is now what P120 did. The earlier stop happened because the loop treated a missing evidence prerequisite as a planning endpoint instead of an executable next step.

## Residual Debt

- Pro aggregate wall ratio remains a soft warning: 1.8078 vs target 1.8.
- Public report should describe GPT-5.5 direct as a teacher reference, not as a same-model uplift arm.
- Wider public benchmark expansion beyond this 8-task teacher suite remains a next launch iteration, not a blocker for the current P120 closure.

## Next Goal

Prepare the public claim package and reduce remaining soft cost warnings without reducing verified delivery or trust safety.

## Next Long Plan

P121: Draft public report with three claims only: same-model verified lift, 8-task GPT-5.5 teacher proximity, and trust-safe delivery.

P122: Add limitation section: GPT-5.5 direct is a teacher reference, not an oracle or same-model uplift baseline.

P123: Optimize Pro aggregate wall warning by lane-specific context/phase slimming.

P124: Re-run P120 gate after Pro cost tuning; require no launch blockers and no hard cost failures.

P125: Promote verified P120 route-cost lessons into learning closure and S2T policy draft.

P126: Validate Autodata manifests remain training-eligible after report generation.

P127: Clean unrelated dirty worktree noise separately from runtime/report artifacts.

P128: Commit P90-P120 gate/report/test artifacts in a coherent commit.

P129: Run final smoke: P120 gate + pre-flash gate + focused tests.

P130: Publish launch-candidate report bundle.
