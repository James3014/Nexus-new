# Nexus Benchmark Policy

Date: 2026-05-05
Status: Accepted

## Purpose

Nexus must not run long benchmarks reflexively. Benchmark scope is selected by the claim being made and the surface changed.

## Required Verification Ladder

| Change type | Required verification | Long benchmark allowed? |
| --- | --- | --- |
| Unit-level runtime change | Targeted pytest only | No |
| Route/report/gate change | Targeted pytest + `python3 scripts/ops/capability_route_smoke.py` | No |
| Research route/checkpoint change | Route smoke + `python3 scripts/ops/research_stack_route_smoke.py` | No |
| Public benchmark/report change | Flash 2x1 or 4x1 regression | No 12x2 unless claim changes |
| Public claim candidate | Flash 12x2 candidate | Yes, only after 4x1 gates pass |
| Pro validation | Explicit decision gate | Never automatic |

## Stop Rules

- If Flash 4x1 passes all public gates and does not produce a new public claim, stop there.
- If a 12x2 run is started only for habit or reassurance, stop it and record the reason.
- If a run produces infra-invalid rows, classify them before interpreting capability quality.

## P148 Lesson

P147 Flash 4x1 was enough to verify Brain Hub guidance, route quality, and public gates after the P137-P146 changes. A 12x2 run was not necessary unless preparing a new public headline claim.
