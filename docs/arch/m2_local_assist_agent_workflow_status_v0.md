# M2 Local Assist Agent Workflow Architecture Status

## Status

`M2_IMPLEMENTED_AWAITING_ONLINE_AGENT_SMOKE`

This document records the current architecture delta for M1/M2. It does not promote automatic dispatch, cloud runtime, production readiness, or public-claim eligibility.

## Current topology

```text
Online Agent
  -> enforced Nexus briefing
  -> explicit nexus local-assist command
  -> LocalAssistService
  -> real Ollama/Qwen provider
  -> response.json + execution_receipt.json
  -> Agent closeout validation
```

`candidate` and `verified-subtask` continue through isolated workspace execution. Deterministic verification remains downstream of candidate generation; Local Assist is not verifier authority. The formal workspace is not mutated by the Local Assist path.

## Capability state

| Capability | State | Evidence boundary |
| --- | --- | --- |
| Explicit advisor/candidate/verified-subtask seam | `PROVEN` | M1 live Ollama receipts and focused service tests |
| Agent-facing command knowledge | `IMPLEMENTED` | enforced briefing and launcher tests |
| Receipt-backed Agent closeout contract | `IMPLEMENTED` | closeout tests and CLI contract smoke |
| Real Ollama invocation | `PROVEN_FOR_M1` | provider ledger, resolved model, call count, delivery fields |
| Agent consumed output in an audited task | `PENDING` | requires an authorized Gemini/Grok task and final closeout |
| Automatic planner dispatch | `NOT_IN_SCOPE` | M3 only |
| Real cloud provider integration | `NOT_IN_SCOPE` | M4 only |
| Causal value measurement | `NOT_IN_SCOPE` | M5 only |

## Claim boundary

The architecture currently proves an explicit, receipt-producing local-assist seam. It does not prove `AGENT_OPERATED_LOCAL_ASSIST_PROVEN`, `outcome_contributed`, or `value_measured`. `local_assist_output_consumed=true` is valid only when the Agent's subsequent operation or final output references every required receipt identity.

## Required next transition

Run one authorized Gemini/Grok audited task that uses advisor plus candidate or verified-subtask, completes a bounded development task, and submits a closeout citing both receipt artifacts. Until that evidence exists, retain the current status and do not start M3.
