# Nexus GPT-5.5 Teacher Distance P231-P360

## Final Goal

Make Gemini 3 Flash and Gemini 3.1 Pro wearing Nexus approach `GPT-5.5 direct` verified delivery on fixed public tasks, without treating `GPT-5.5+Nexus` as the target.

## Runs

| Run | Arm | Verified | Avg wall | Avg tokens | Public gate |
| :--- | :--- | ---: | ---: | ---: | :--- |
| P231-P240 | GPT-5.5 direct | 3/4 | 9.1486s | 13,899.5 | PASS |
| P231-P240 | GPT-5.5+Nexus | 4/4 | 20.0929s | 19,003.0 | PASS |
| P241-P255 | Gemini 3 Flash bare | 1/4 | 18.4559s | 43,820.25 | PASS |
| P241-P255 | Gemini 3 Flash+Nexus forced hyper | 4/4 | 100.095s | 58,628.25 | PASS |
| P256-P270 | Gemini 3.1 Pro bare | 1/4 | 51.0314s | 41,246.25 | PASS |
| P256-P270 | Gemini 3.1 Pro+Nexus forced hyper | 4/4 | 57.8957s | 63,365.25 | PASS |
| P286-P305 | Gemini 3 Flash+Nexus auto route | 4/4 | 69.6084s | 68,897.25 | PASS |
| P306-P320 | Gemini 3 Flash+Nexus global lite route | 2/4 | 46.2166s | 44,011.5 | not promoted |
| P321-P340 | Gemini 3 Flash+Nexus task policy | 4/4 | 68.4777s | 69,781.0 | not promoted |

## What We Learned

- Gemini 3 Flash+Nexus reached 4/4 verified while Flash bare reached 1/4.
- Gemini 3.1 Pro+Nexus reached 4/4 verified while Pro bare reached 1/4.
- GPT-5.5 direct reached 3/4, so the teacher is a measured reference, not an oracle.
- Auto route reduced Flash wall time versus forced hyper, but did not reduce token cost.
- Global lite route reduced cost but broke verified delivery, so it must not be promoted.
- Task-specific lite route preserved verified delivery, but did not improve aggregate cost enough to promote.

## Diagnosis

The main cost driver is not only candidate count. The high-cost `research` capability is still selected on every Flash auto-route row, and governance/evidence tasks need heavier control to preserve verified delivery.

The route-cost bug found in this round was narrower: environment-level `NEXUS_ROUTE_COST_CONTROLS` reached the planner but did not reach executor-level candidate/self-heal controls. That wiring is now fixed and covered by tests.

## Evidence Files

- `.nexus/reports/p231_p240_codex55_direct_teacher_4task/evidence_bundle.json`
- `.nexus/reports/p241_p255_flash_teacher_tasks_4task/evidence_bundle.json`
- `.nexus/reports/p256_p270_pro_teacher_tasks_4task/evidence_bundle.json`
- `.nexus/reports/p286_p305_flash_auto_route_4task/evidence_bundle.json`
- `.nexus/reports/p306_p320_flash_lite_route_4task/evidence_bundle.json`
- `.nexus/reports/p321_p340_flash_task_policy_4task/evidence_bundle.json`
- `.nexus/reports/p271_p285_flash_vs_gpt55_direct_gap.json`
- `.nexus/reports/p271_p285_pro_vs_gpt55_direct_gap.json`
- `.nexus/reports/p306_p320_flash_auto_vs_gpt55_direct_gap.json`

## Closure

P231-P360 achieved the core measurement goal: Flash/Pro wearing Nexus can match or exceed GPT-5.5 direct verified delivery on this fixed task set, but current Nexus cost is still too high for always-on use.

The next closure target is not more broad benchmark running. It is route-cost reduction that preserves 4/4 verified delivery, especially removing unnecessary high-cost `research` selection where no external research evidence is needed.
