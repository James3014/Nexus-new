# Hermes Local Continuation Controller Pilot — H1–H5

Date: 2026-10-04
Tracking: James3014/Nexus-new#1386
Execution lane: bounded direct pilot; no production activation
AUTO_CHAIN: false

## Scope and authority

This pilot proves a local-first Hermes continuation layer without creating a
second Nexus authority.

- Hermes/Qwen may reason, use tools, and resume sessions.
- Nexus Core remains evidence/completion authority.
- workflow doctor remains read-only workflow observation.
- CapabilityPlanner remains route/capability authority where applicable.
- nexus-agy-dispatch remains Agy lease/quota/operation authority.
- Frontier-model answers are advisory only.
- No merge, release, deployment, or production authority is granted here.

## Local runtime

Observed Mac mini:
- Apple M5 Pro
- 20-core GPU
- 64 GB unified memory
- Splash 1.0.2
- Hermes v0.21.5+6694.gf10a763
- local model: incoai/Qwen3.6-35B-A3B-Splash
- configured context: 65,536
- local endpoint: http://127.0.0.1:8000/v1

Hermes main model and auxiliary goal_judge were both bound to the same local
Splash endpoint for the local canaries.

## H1 — Nexus Core governance: PASS

A standalone fixture repository was initialized with nexus-certify==0.1.1.

First Hermes attempt was instructed to write `GOOD\n` but physically produced
`GOOD` without the newline. Nexus Core rejected it:

- result: `FAILED_VERIFICATION (not CERTIFIED)`
- reason: `VERIFIER_FAILED`

Hermes then repaired the exact bytes to `47 4f 4f 44 0a`.
Nexus Core returned:

- `VERIFIED (not CERTIFIED)`
- receipt:
  `20261004T033429.671696+0000-d29980caf328.json`

Negative controls:
- forbidden path -> `FORBIDDEN_PATH`, exit 2
- verifier failure -> `FAILED_VERIFICATION`, exit 1
- repaired final state -> `VERIFIED (not CERTIFIED)`

Conclusion: local-model completion prose cannot override deterministic evidence.

## H2 — Read-only workflow interpretation: PASS

Added `scripts/ops/nexus-hermes-controller-guard`.

The guard validates:
- `schema == nexus.workflow_doctor.v1`
- `claim_ceiling == READ_ONLY_WORKFLOW_OBSERVATION`

Deterministic dispositions:
- SAFE -> exact-next-gate / terminal-noop projection
- WAIT -> WAIT
- RECONCILE -> RECONCILE_EXISTING_EFFECT
- BLOCKED -> BLOCK
- unknown/malformed -> BLOCK_UNKNOWN

`--require-safe` returns non-zero for non-SAFE observations, preventing a shell
chain from dispatching merely because doctor output was printed.

## H3 — Frontier adviser escalation: PASS with current transport

Escalation is deterministic, not based on local-model self-confidence.

Current triggers:
- same gate failed >= 2 times
- evidence conflict
- authority-boundary change
- irreversible effect
- reviewer/worker conflict
- >= 2 plausible root causes after bounded falsification is exhausted

The guard emits `ASK_FRONTIER_ADVISER` with `authority=ADVISORY_ONLY`.

Physical adviser canary:
- Hermes provider: GitHub Copilot
- model: GPT-4.1
- prompt invariant: `OUTCOME_UNKNOWN != retry permission`
- response: `RECONCILE_ORIGINAL_EFFECT`
- exit: 0

OpenAI API transport was also probed but failed closed because no usable
`OPENAI_API_KEY` was available to the new Hermes process. No API fallback or
billing was used.

ChatGPT/Codex OAuth remains a separate optional transport improvement; it is
not required for the adviser contract proven here.

## H4 — Canonical Agy dispatch: PASS after guard correction

An initial harmless transport canary was accidentally launched after doctor had
reported `BLOCKED / SOURCE_IDENTITY_UNAVAILABLE` because the shell command did
not gate execution on the doctor result.

That operation was harmless (plan mode, no tools) and completed:
- operation: `agyop_7f013e2e284e477c84bb9988a5da2b33`
- stdout: `H4_AGY_CANARY_OK`
- tool events: 0
- source attribution: unavailable

This exposed and motivated the `--require-safe` regression guard.

The governed-source canary was then rerun from a real Git fixture, with the
guard required to exit successfully before dispatch:
- operation: `agyop_1af41b3ab4fa44b9aeefc3fa25ae9896`
- base_head: `cb1c54f4e5660561cab4b274190d8676c4487622`
- source_attribution_state: `ATTRIBUTED`
- status: `COMPLETED`
- exit_code: 0
- tool_event_count: 0
- rotations: 0

No Hermes Antigravity plugin was used. Account/lease/operation authority stayed
inside `nexus-agy-dispatch`.

## H5 — restart / fault safety: PASS for safety semantics

Hermes durable session restart:
- session: `20261004_053408_72c9e2`
- session resumed after process termination
- `/goal status` returned `Goal done (1/20 turns)`

Guard restart soak:
- 25 cycles
- each invocation was a fresh process
- SAFE cases passed `--require-safe`
- WAIT / RECONCILE / BLOCKED each exited 3
- result: `H5_GUARD_SOAK_PASS_25_CYCLES`

Agy lost-ack/timeout fault injection:
- operation: `agyop_971546858070446d863740713cffd79c`
- timeout: 1 second
- status: `OUTCOME_UNKNOWN`
- failure_kind: `TIMEOUT`
- tool_event_count: 0
- reconciliation: `PROVIDER_TURN_MAY_STILL_BE_RUNNING`
- retry_permitted: false

The exact same operation was reconciled. No replacement operation was launched.
The canonical record intentionally remains `OUTCOME_UNKNOWN`; the pilot does
not manufacture completion from process death, empty stdout, or absence of tool
events.

## Result

H1–H5 establish the bounded architecture:

```text
Hermes + local Qwen
        |
        +-- deterministic controller guard
        |
        +-- Nexus Core evidence/completion
        |
        +-- workflow doctor observation
        |
        +-- frontier adviser (advisory only)
        |
        +-- nexus-agy-dispatch (canonical Agy effects)
```

The pilot does not establish production readiness or 24/7 unattended operation.
A multi-hour wall-clock soak remains a separate activation gate; this bounded
pilot proves restart, deterministic disposition handling, fail-closed evidence,
canonical dispatch attribution, and no-blind-retry behavior.
