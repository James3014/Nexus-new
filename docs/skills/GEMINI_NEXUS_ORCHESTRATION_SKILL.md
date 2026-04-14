# GEMINI+NEXUS Orchestration Skill (Codex Supervisor)

## Purpose
Standardize this workflow so it is repeatable:
1. Codex plans work.
2. Codex delegates implementation to `gemini+nexus`.
3. Codex validates outputs and gates.
4. If not passing, Codex issues next-round tasks.

This skill avoids ad-hoc prompting and forgotten steps.

## Preconditions
1. Workdir: `/Users/jameschen/Workspace/nexus`
2. `gemini` binary exists at `/Users/jameschen/.npm-global/bin/gemini`
3. Use `scripts/ops/gemini_nexus_invoke.py` (single-flight lock + retry + classification)

## Standard Loop
### Step A: Prepare Task Prompt
Create a short-cycle prompt file:
- Scope files (max 10)
- Required commands
- Required output line
- No fake completion wording if thresholds not met

Template:
```md
[NEXUS v22 ACTIVE] <round-name>

Scope:
- <file1>
- <file2>

Goal:
- <clear measurable goal>

Required commands:
- <test command 1>
- <benchmark command 2>

Output format:
- modified files
- commands + key outputs
- final line:
Validated benchmark. algorithm_success_rate=<x>. regression_rate=<y>. infra_blocked_rate=<z>. thresholds met/not met.
```

### Step B: Dispatch Gemini+Nexus
Always run preflight first to detect channel health before a heavy prompt:
```bash
cd /Users/jameschen/Workspace/nexus
uv run python3 scripts/ops/gemini_nexus_invoke.py \
  --preflight \
  --preflight-only \
  --prompt "reply with exactly: OK" \
  --timeout-sec 30 \
  --max-retries 0 \
  --report-file .nexus/reports/gemini_preflight.json
```

If preflight is `OK`, run delegation with short-cycle timeout first:
```bash
cd /Users/jameschen/Workspace/nexus
rm -f /private/tmp/nexus_gemini_invoke.lock
uv run python3 scripts/ops/gemini_nexus_invoke.py \
  --prompt-file /tmp/<round_task>.md \
  --timeout-sec 180 \
  --inactivity-timeout-sec 90 \
  --max-retries 0 \
  --report-file .nexus/reports/gemini_<round>_report.json
```

Only use long timeout (e.g. 700) after one successful short-cycle round in the same session.

### Step C: Supervisor Validation (Codex)
Run required validations yourself, do not trust only narrative:
```bash
uv run pytest -q <targeted-tests>
uv run scripts/engine/nexus_cli.py nexus research:benchmark --manifest-file <manifest> --mode ab --ab-trials 2 --report-file <report>
```

Parse report and compute:
1. `algorithm_success_rate`
2. `regression_rate`
3. `infra_blocked_rate`

### Step D: Gate Decision
Pass only if all met:
1. `algorithm_success_rate >= 0.55`
2. `regression_rate <= 0.05`
3. `infra_blocked_rate <= 0.20`

If failed:
1. Produce RCA from report fields
2. Issue next-round prompt only for top failure class
3. Repeat Step B/C

## Known Failure Modes + Handling
1. `single_flight_lock_active`
- Fix: `rm -f /private/tmp/nexus_gemini_invoke.lock`

2. `AUTH_LOOP`
- Fix: run interactive gemini once; then retry invoke

3. `TIMEOUT` (even when preflight is OK)
- Interpretation: delegation channel is alive, but prompt scope is too heavy for current session/model latency.
- Fix sequence (mandatory):
  - kill stale invoke processes + clear lock
  - split into short-cycle prompt (one blocker, 1-3 files)
  - keep timeout at 180-240
  - supervisor runs benchmark locally after code patch
  - if 2 consecutive `TIMEOUT` on short-cycle, mark `gemini_delegation_blocked` and fallback to local implementation for this round

4. `preflight_failed` (classification is timeout)
- Interpretation: current Gemini session is not healthy enough for delegated coding, even for probe prompts.
- Fix sequence (mandatory):
  - run one interactive `gemini` check in terminal
  - re-run preflight-only once
  - if still fails, set `gemini_delegation_blocked` and proceed with local implementation + supervisor verification

4. Benchmark blocked by `semantic_guard/stage1_failed`
- Fix: prioritize stage1 + semantic guard interop, not timeout tuning first

## Reporting Contract (Supervisor Output)
Always include:
1. What was delegated
2. What was verified by command output
3. Current gate status
4. Next-round plan if not met

Final metric line:
`Validated benchmark. algorithm_success_rate=<x>. regression_rate=<y>. infra_blocked_rate=<z>. thresholds met/not met.`
