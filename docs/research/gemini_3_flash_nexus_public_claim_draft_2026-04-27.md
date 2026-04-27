# Gemini 3 Flash + Nexus Public Claim Draft

Status: public candidate

## Claim Boundary

Nexus is the battlesuit. Gemini remains the model doing the work; Nexus adds routing, scoped context, governance, verification, artifact evidence, self-heal, local rescue, guard fallback, and closure telemetry.

This draft only covers `gemini-3-flash-preview`. It does not mix `gemini-3.1-pro-preview`.

## Primary Claim Candidate

Source:

- `.nexus/reports/bench_gemini3flash_value12x2_public_final/without_nexus_1777301310.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x2_public_final/with_nexus_1777301310.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x2_public_final/gemini_nexus_report_1777301310.md`

Protocol:

- Model: `gemini-3-flash-preview`
- 12 unique hidden-verifier tasks
- 2 trials per task
- `hidden_verifier_mode=true`
- `public claim gate=PASS`

Result:

| Metric | Gemini 3 Flash bare | Gemini 3 Flash + Nexus |
| --- | ---: | ---: |
| Usable rows | 23/24 | 24/24 |
| Infra invalid rows | 1 | 0 |
| Solve rate | 29.2% | 100.0% |
| Semantic verified | 29.2% | 100.0% |
| Trust mismatch | 0.0% | 0.0% |
| Avg wall time | 109.54s | 72.30s |
| Wall speedup | n/a | 34.0% |
| Avg model calls | 1.00 | 1.67 |
| Token measured rate | 91.7% | 100.0% |
| Token public-safe claim | YES | YES |
| LLM self-heal rate | 0.0% | 58.3% |
| Local rescue rate | 0.0% | 8.3% |
| Guard fallback rate | 0.0% | 8.3% |
| Nexus wearing evidence | n/a | 24/24 |
| Phase completion | n/a | 24/24 |
| Claim verified | n/a | 24/24 |

Allowed claim:

> On a 12-task hidden-verifier engineering benchmark with 2 trials per task, using `gemini-3-flash-preview`, Gemini 3 Flash + Nexus improved semantic verified rate from 29.2% to 100.0% (+70.8 percentage points), improved average wall time by 34.0%, and kept trust mismatch at 0.0%. Nexus provided valid wearing evidence, six-phase completion, and claim verification for all 24 treatment rows.

Required caveat:

> This is a frozen benchmark result, not a universal guarantee. Publish raw JSONL, evidence bundle, model name, command, and limitations with the claim.

Not allowed:

- Claiming Nexus always improves solve rate by 70.8 points.
- Claiming Nexus is a separate solving agent.
- Mixing this result with `gemini-3.1-pro-preview`.

## Product Value Statement

Use:

> Nexus turns Gemini from a one-shot coding model invocation into a governed engineering loop. In the hidden-verifier benchmark, the lift came from self-heal, artifact verification, local rescue, guard fallback, scoped governance, and machine-readable closure evidence.

Avoid:

> Nexus is a separate agent that solves instead of Gemini.

Avoid:

> Nexus always beats Gemini on every task.

## Publication Checklist

- Include raw `with_nexus` and `without_nexus` JSONL.
- Include `evidence_bundle.json`.
- Include generated markdown benchmark report.
- Include command and environment variables.
- State model exactly: `gemini-3-flash-preview`.
- State `hidden_verifier_mode=true`.
- State `Public claim gate: PASS`.
