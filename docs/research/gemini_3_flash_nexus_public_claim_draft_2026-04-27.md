# Gemini 3 Flash + Nexus Public Claim Draft

Status: public candidate, needs repeat-run confirmation

## Claim Boundary

Nexus is the battlesuit. Gemini remains the model doing the work; Nexus adds routing, scoped context, governance, verification, artifact evidence, self-heal, and closure telemetry.

This draft only covers `gemini-3-flash-preview`. It does not mix `gemini-3.1-pro-preview`.

## Primary Claim Candidate

Source:

- `.nexus/reports/bench_gemini3flash_value12x1_hidden_timeoutfix_full12/without_nexus_1777293163.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x1_hidden_timeoutfix_full12/with_nexus_1777293163.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x1_hidden_timeoutfix_full12/gemini_nexus_report_1777293163.md`

Protocol:

- Model: `gemini-3-flash-preview`
- 12 unique hidden-verifier tasks
- 1 trial
- `hidden_verifier_mode=true`
- `public claim gate=PASS`

Result:

| Metric | Gemini 3 Flash bare | Gemini 3 Flash + Nexus |
| --- | ---: | ---: |
| Usable rows | 12/12 | 12/12 |
| Infra invalid rows | 0 | 0 |
| Solve rate | 25.0% | 100.0% |
| Semantic verified | 25.0% | 100.0% |
| Trust mismatch | 0.0% | 0.0% |
| Avg wall time | 42.82s | 54.99s |
| Avg model calls | 1.00 | 1.67 |
| Token measured rate | 91.7% | 100.0% |
| LLM self-heal rate | 0.0% | 66.7% |
| Nexus wearing evidence | n/a | 12/12 |
| Phase completion | n/a | 12/12 |
| Claim verified | n/a | 12/12 |

Allowed claim:

> On a 12-task hidden-verifier engineering benchmark using `gemini-3-flash-preview`, Gemini 3 Flash + Nexus improved semantic verified rate from 25.0% to 100.0% (+75.0 percentage points) while keeping trust mismatch at 0.0%. Nexus provided valid wearing evidence, six-phase completion, and claim verification for all 12 treatment rows.

Required caveat:

> This is a 12-task x 1-trial public candidate. Before making a publication-grade claim, repeat the same protocol for 12x2 or 12x3 and publish the raw JSONL/evidence bundle.

Not allowed:

- Claiming Nexus always improves solve rate by 75 points.
- Claiming Nexus is faster.
- Claiming Nexus uses fewer model calls.
- Mixing this result with `gemini-3.1-pro-preview`.

## Product Value Statement

Use:

> Nexus turns Gemini from a one-shot coding model invocation into a governed engineering loop. In the hidden-verifier benchmark, the lift came from self-heal, artifact verification, scoped governance, and machine-readable closure evidence.

Avoid:

> Nexus is a separate agent that solves instead of Gemini.

Avoid:

> Nexus always beats Gemini on every task.

## Publication Gate For Next Run

Before external publication:

- Run 12x2 or 12x3 with the same task IDs.
- `NEXUS_VALUE_HIDDEN_VERIFIER=1` must be recorded as true.
- `Public claim gate: PASS`.
- Nexus wearing evidence at least 95%, preferred 100%.
- Infra invalid rows reported separately and ideally zero.
- Trust mismatch reported and not hidden.
- Raw JSONL, evidence bundle, markdown report, command, model name, and quota/model fallback notes included in appendix.
