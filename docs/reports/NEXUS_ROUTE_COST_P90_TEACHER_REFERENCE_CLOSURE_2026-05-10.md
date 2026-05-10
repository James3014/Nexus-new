# Nexus Route Cost P90 Teacher Reference Closure

Date: 2026-05-10

## Final Target

Gemini 3 Flash and Gemini 3.1 Pro wearing Nexus should approach GPT-5.5 direct on fixed public tasks, without using GPT-5.5+Nexus as the target, while preserving:

- verified delivery lift
- trust mismatch = 0
- same-model public claim discipline
- cost low enough for always-on routing

## P90 Result

P90 passes for the current fixed 4-task GPT-5.5 teacher-reference slice.

The reference is `.nexus/reports/p231_p240_codex55_direct_teacher_4task` using the `without_nexus` arm. That run is the public-gate-passing GPT-5.5 direct teacher baseline for this closure check.

## Data

| Arm | Teacher-overlap verified rate | Teacher verified rate | Delta vs teacher | Trust mismatch | Public gate | Wall ratio | Token ratio |
|---|---:|---:|---:|---:|---|---:|---:|
| GPT-5.5 direct teacher | 0.75 | 0.75 | 0.00 | 0 | PASS | 1.0000 | 1.0000 |
| Gemini 3 Flash + Nexus P72 | 1.00 | 0.75 | +0.25 | 0 | PASS | 1.6048 | 1.1098 |
| Gemini 3.1 Pro + Nexus P73 | 1.00 | 0.75 | +0.25 | 0 | PASS | 1.8078 | 1.1285 |

The broader same-model evidence remains:

- Flash P72: Nexus 16/16 verified vs bare 11/16, trust mismatch 0, public gate PASS.
- Pro P73: Nexus 8/8 verified vs bare 5/8, trust mismatch 0, public gate PASS.

## Evidence

- GPT-5.5 direct teacher: `.nexus/reports/p231_p240_codex55_direct_teacher_4task/evidence_bundle.json`
- Flash same-model evidence: `.nexus/reports/flash_8x2_p72_policy_preflight/evidence_bundle.json`
- Pro same-model evidence: `.nexus/reports/pro_8x1_p73_policy_preflight/evidence_bundle.json`
- Teacher reference gate: `.nexus/reports/p90_teacher_reference_gate.json`
- Flash teacher gap matrix: `.nexus/reports/p76_p90_flash_vs_gpt55_direct_gap.md`
- Pro teacher gap matrix: `.nexus/reports/p76_p90_pro_vs_gpt55_direct_gap.md`

## Verification

Commands:

```bash
uv run pytest -q tests/benchmark/test_teacher_reference_gate.py tests/benchmark/test_route_decision_simulator.py tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_route_cost_optimizer.py tests/app/test_research_flow_service.py tests/engine/test_capability_receipt_adapters.py tests/nexus/codeintel/test_dci_locator.py
uv run python scripts/ops/nexus_pre_flash_gate.py --quick
uv run python scripts/bench/teacher_reference_gate.py --teacher-run .nexus/reports/p231_p240_codex55_direct_teacher_4task --teacher-arm without_nexus --student flash_p72=.nexus/reports/flash_8x2_p72_policy_preflight --student pro_p73=.nexus/reports/pro_8x1_p73_policy_preflight --output .nexus/reports/p90_teacher_reference_gate.json
```

Observed:

- 273 tests passed.
- Pre-Flash gate passed.
- Teacher reference gate passed.

## Residual Debt

P90 is not a full public launch claim. It is a closure gate for the current fixed teacher-reference slice.

Remaining issues:

- Pro wall ratio is 1.8078, slightly above the 1.8 target.
- Teacher-reference overlap is 4 tasks; the next public claim should expand the fixed teacher set to 8-12 tasks.
- Teacher gap matrices show several tasks where Nexus is quality-positive but runtime/token-heavy, especially belief/evidence/governance tasks.

## Next Long Plan

P91: Expand GPT-5.5 direct teacher reference from 4 tasks to 8-12 fixed tasks, using only public-gate-valid tasks.

P92: Add a strict report gate that separates "approaches GPT-5.5 quality" from "cost acceptable for always-on"; both must be visible.

P93: Reduce Pro P73 wall ratio below 1.8 without lowering verified delivery or increasing trust mismatch.

P94: Target high-cost teacher-gap rows first: belief, evidence, and governance.

P95: Add route-policy regression tests that prevent task-id-specific overfitting; decisions must be feature/lane based.

P96: Feed P72/P73/P90 traces into the Nexus learning closure and model-training export path as verified experience rows.

P97: Re-run Flash and Pro same-model A/B after cost changes; stop on first fail, inspect trace, patch, then continue.

P98: Prepare a public report draft with limitation language: same-model lift is proven; GPT-5.5 teacher proximity is proven only on the current fixed slice until expanded.

P99: Clean dirty worktree into coherent commits.

P100: Launch-candidate gate: same-model public gate PASS, teacher-reference gate PASS, trust mismatch 0, and no cost warning above target.
