# TASK-005 — Explicit OpenCLI Web pacing and bounded-turn transport

task_id: `TASK-005`

- **Campaign:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `ACTIVE`
- **Authority:** Owner-authorized sanitized Ready reconciliation on GitHub Issue #695
- **Source delta:** `NEXUS_CONTROLLER_HANDOFF_V2` H9-H13
- **Auto-chain:** `false`
- **Maximum claim:** `IMPLEMENTER_PASS_PENDING_ACCEPTANCE`
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Execution lane:** GitHub Ready-Issue branch, primary direct implementation
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`

## Goal

Implement the H11 pacing contract inside the external Open SWE runtime while preserving explicit OpenCLI transport binding and all existing Nexus authority, tool, credential, repair-scope, and reconciliation boundaries.

## Frozen H11 transport contract

- OpenCLI CLI/daemon: `1.8.7`
- Browser Bridge: `1.0.24`
- executable: explicit absolute path at runtime; no ambient PATH guessing
- profile: explicit connected OpenCLI profile; no default-profile guessing
- site-session mode: explicit `persistent`; accepted domain is only `ephemeral|persistent`
- timeout: explicit bounded seconds; current qualification value `120`
- intelligence: explicit `very-high`
- `MAX_INFLIGHT_PER_SITE_SESSION=1`
- `MIN_WEB_SEND_INTERVAL_SECONDS=15`
- `POST_RESPONSE_SETTLE_SECONDS=3`
- `MAX_WEB_TURNS_PER_OPERATION=12`
- model selection: idempotent, maximum one retry, delay at least 10 seconds
- original semantic ask: exactly one initial send; timeout/uncertainty never authorizes redispatch
- busy/rate-control: cooldown at least 60 seconds before read-only status probe; no prompt resend
- login/challenge/quota: hard block; no automated retry

## Observable behavior

Two model instances sharing one explicit profile/site-session cannot overlap semantic Web sends. Back-to-back tool-result turns are delayed to the send-start and response-stability thresholds. Protocol-repair sends are distinct, paced, and counted. Turn 13 fails closed without a Web send. Read-only history/detail/status reconciliation is not counted as a semantic send and cannot redispatch the original ask.

## Allowed paths

Production:

- `runtimes/open_swe/nexus_open_swe_runtime/opencli_web_model.py`
- `runtimes/open_swe/nexus_open_swe_runtime/cli.py`
- `nexus/services/open_swe_external_intelligence.py`

Tests:

- `runtimes/open_swe/tests/test_opencli_web_model.py`
- `tests/services/test_open_swe_external_intelligence.py`
- existing process-death tests may be executed but not edited

No other file may be edited by the implementation commit. No deletion is allowed.

## Required RED controls

1. Two shared-session model instances cannot issue overlapping semantic asks.
2. Fake monotonic clock proves at least 15 seconds between semantic send starts.
3. Detail/readback requires at least 3 seconds stable response evidence.
4. Selector retry occurs only after at least 10 seconds.
5. Login/challenge/quota errors never enter selector retry.
6. Invalid site-session modes fail before subprocess dispatch.
7. Original ask timeout performs history/detail reconciliation with ask count exactly one.
8. Refresh/detail does not increment ask count.
9. Protocol repair is separately identified and consumes the Web-turn budget.
10. Turn 13 fails closed before subprocess dispatch.
11. No subprocess invocation uses `shell=true`.
12. Undeclared tools remain rejected.

## Implementation constraints

- Use injectable monotonic clock/sleeper seams; unit tests must not actually sleep.
- Use a bounded runtime-local shared pacing gate keyed by explicit executable/profile/site-session identity; do not create a queue, router, scheduler authority, durable lifecycle, or cross-process graph checkpoint.
- Pace only semantic/repair sends. Model-selection retry has its separate 10-second delay. History/detail/status are read-only reconciliation.
- Preserve one-write original ask, deterministic turn identity, conversation drift rejection, and `OUTCOME_UNKNOWN -> retry_safe=false`.
- Preserve semantic/diagnosis read-only tool surfaces, bounded repair paths, environment allowlist, and `shell=false`.
- OpenCLI/ChatGPT output is implementation evidence only, never acceptance authority.

## Verification

```text
uv run --project runtimes/open_swe pytest -p no:cacheprovider runtimes/open_swe/tests/test_opencli_web_model.py
uv run pytest -p no:cacheprovider tests/services/test_open_swe_external_intelligence.py tests/services/test_open_swe_process_death.py
uv run --project runtimes/open_swe ruff check runtimes/open_swe/nexus_open_swe_runtime runtimes/open_swe/tests
uv run pyright nexus/services/open_swe_external_intelligence.py
uv run pyright --pythonpath runtimes/open_swe/.venv/bin/python runtimes/open_swe/nexus_open_swe_runtime nexus/services/open_swe_external_intelligence.py
uv run bandit -q -r nexus/services/open_swe_external_intelligence.py runtimes/open_swe/nexus_open_swe_runtime
git diff --check
```

The combined Pyright and Bandit commands are exact-base classifiers: Candidate PASS requires `new_errors=0` and `new_findings=0`, not a false claim that pre-existing baseline findings are absent. Exact-base comparison, full diff/scope/deletion inspection, and independent H13 review are separate from Implementer PASS.

## Exit

- PASS: exact scoped Candidate commit/tree/diff plus required deterministic and regression checks; stop implementation claim at `IMPLEMENTER_PASS_PENDING_ACCEPTANCE`.
- BLOCK: duplicate-send possibility, session binding ambiguity, scope escape, security/authority regression, or required verifier failure.
- Next gate: H13 independent acceptance; no live Web qualification implied.
