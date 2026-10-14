# Hybrid replication: opening a generation (runbook)

Scope: James3014/Nexus-new#1216. Authority: `RESEARCH_OBSERVATION_ONLY`. This runbook
applies design-review decisions D1 to D5 (`DESIGN_REVIEW_20261011.md`, section 4):

- D1: the runtime is an immutable artifact outside `main` (detached worktree plus a
  pinned dispatcher copy). The live binding JSON is the identity authority.
- D2: protocol loss is per task, not per generation.
- D3: campaign meta-work is excluded from the primary cohort.
- D4: one activation manifest and one script write the repository variables.
- D5: readiness requires a control that reaches DM1.

Machine-readable counterpart: `AUTOMATION_CONTRACT.json` (`activation`, `fail_close`,
`primary_cohort_exclusions`, `activation_manifest`, `live_binding`). The first manifest is
`activation/V11.manifest.json`. Steps marked "host (Mac mini)" run only on the machine that
holds the live root, the launchd service and `gh` credentials for the 8 repositories.
Every step has a stop condition; on a stop, do not continue to the next step.

Placeholders used below:

| Placeholder | Meaning |
|---|---|
| `<SHA>` | 40-hex source commit chosen in step 0 |
| `<LIVE_ROOT>` | live root on the host, for example `~/nexus-hybrid-deployment-replication-20260930` |
| `<BASE_BINDING>` | existing binding JSON used as template (previous `LIVE_BINDING.json`) |
| `<BINDING>` | new binding written by step 1, `<LIVE_ROOT>/live/LIVE_BINDING.V11.json` |
| `<RUNTIME>` | `<LIVE_ROOT>/runtime/<SHA>` (printed as `runtime_root` by step 1) |
| `<STORE_ROOT>` | automatic replication store root used by the daemon |
| `<CONTROL_KEY>` | readiness control task key, `James3014/Nexus-new#<N>` |

## 0. Preconditions

1. The branch carrying `hybrid_replication_freeze_runtime.py`, `RUNBOOK.md` and
   `activation/V11.manifest.json` is merged to `main`. Stop if not merged.
2. The Owner has fixed the D6 numbers (primary denominator unit, stop count, expected
   confidence interval; proposal in `DESIGN_REVIEW_20261011.md` section 6). Stop if they
   are not recorded on #1216.
3. All eight candidate repositories run the pinned reusable capture caller
   (`capture_caller.template.yml`), so the D3 campaign exclusion applies everywhere.
   Stop if any repository still has the old inline copy.
4. A source SHA is chosen: the `main` commit whose runtime is to be frozen. After step 1 it
   no longer matters what `main` does.

```
git -C <source-checkout> rev-parse --verify <SHA>^{commit}
```

Expected: prints `<SHA>`. Stop if it prints anything else or exits non-zero.

## 1. Freeze the runtime (D1)

host (Mac mini). Dry run first; it touches nothing.

```
uv run python scripts/ops/hybrid_replication_freeze_runtime.py \
  --source-repo <source-checkout> --revision <SHA> \
  --live-root <LIVE_ROOT> --generation AGY_GEMINI_3_8_FLASH_MEDIUM_V11 \
  --base-binding <BASE_BINDING> --output-binding <BINDING> --dry-run
```

Then run it without `--dry-run`. Expected on stdout: a JSON receipt with
`schema: nexus.hybrid_replication.runtime_freeze.v1`, `revision` equal to `<SHA>`,
`runtime_root`, `dispatcher_pin_path`, `dispatcher_sha256`, `output_binding`,
`output_binding_sha256` and `reused`. Exit 0.

What it does: creates the detached worktree `<LIVE_ROOT>/runtime/<SHA>` (or reuses it when
its HEAD equals `<SHA>`); copies `scripts/ops/nexus-agy-dispatch` to
`<LIVE_ROOT>/runtime-pins/<generation>/nexus-agy-dispatch` with mode 0555 (create-only);
writes `<BINDING>` as a copy of `<BASE_BINDING>` with `strong_online.provider="agy"`,
`strong_online.agy_dispatch_path`, `strong_online.agy_dispatch_sha256`,
`strong_online.execution_generation`, `source_revision`, `runtime_root` and
`activation_state="NOT_READY"`. Stale top-level and `agy.*` dispatcher keys are removed.

Stop conditions:

- Exit 1: bad generation (must match `^AGY_[A-Z0-9_]+_V\d+$`), revision not 40-hex or not a
  commit in the source repo, unreadable or wrong-schema base binding.
- Exit 2: `<BINDING>` already exists (never overwritten; choose a new path); runtime
  directory exists at another HEAD; pin exists with different content (a generation label
  is never reused for different content; choose a new label).

Record `dispatcher_sha256` and `output_binding_sha256` on #1216.

## 2. Identity preflight

host (Mac mini). Run from the frozen runtime so the code under test is the frozen code:

```
cd <RUNTIME>
uv run python -m nexus.research.hybrid_replication_live identity-preflight --binding <BINDING>
```

The binding may be `NOT_READY` here; this subcommand loads it with activation checks off.
It validates the frozen receipts and D0 files, resolves the pinned dispatcher against
`strong_online.agy_dispatch_sha256`, calls Jev with a synthetic task, and prints one JSON
receipt (`schema: nexus.hybrid_replication.identity_preflight.v3`, with
`execution_generation`, `agy_dispatch_sha256`, `activation_allowed`).

Expected: exit 0 and `"activation_allowed": true`. Stop on exit 5
(`BLOCKED_IDENTITY_OR_PROVIDER_DRIFT`) or on any raised error such as
`agy_dispatch_hash_drift`, `agy_execution_generation_identity_drift` or
`frozen_receipt_binding_set_mismatch`. Fix the binding by creating a new output path; do
not edit the pin.

## 3. Push the manifest as NOT_READY, then read back (D4)

`activation/V11.manifest.json` is committed with `activation_state: NOT_READY`,
`t_auto: null`, `excluded_tasks: []`, `readiness_control_token: ""` and the 8 default
repositories. Copy it to the experiment root if the manifest must live outside the checkout;
the activation script accepts any path.

```
uv run python scripts/ops/hybrid_replication_activation.py push \
  --manifest docs/research/hybrid_replication_v2/activation/V11.manifest.json
uv run python scripts/ops/hybrid_replication_activation.py readback \
  --manifest docs/research/hybrid_replication_v2/activation/V11.manifest.json
```

Expected: `push` exit 0 with `"failures": []`; `readback` exit 0 with `"drift": []`. Stop on
`push` exit 3 (some `gh variable set`/`delete` failed) or `readback` exit 2 (drift). The five
variables are `NEXUS_HYBRID_REPLICATION_ACTIVATION_STATE`, `_T_AUTO`, `_EXCLUDED_TASKS`,
`_EXCLUSION_SET_SHA256`, `_READINESS_CONTROL_TOKEN` (see `AUTOMATION_CONTRACT.json`
`activation.*_variable`). Do not set them by hand. Empty values are applied by deleting the
variable (the GitHub API rejects empty values), and `readback` treats an absent variable as
empty. The activation script is an operator tool run from a current `main` checkout, not from
the frozen `<RUNTIME>` (nothing in the frozen runtime imports it).

## 4. Readiness control Issue (D5)

Note: the capture workflow has no general author filter. Issues created with the workflow
`GITHUB_TOKEN` (for example the nightly regression bot, login `github-actions[bot]`) do not
trigger workflows, so they are never captured. Ingest and the full watchdog therefore exclude
a GITHUB_TOKEN-authored issue that has no capture comment from the expected set and list it in
the non-failing `not_captured_github_token_issue` field; if such an issue does carry a capture
comment it is mirrored normally.

1. Choose a random token. Set `readiness_control_token` to it in the manifest and push and
   read back as in step 3 (state stays `NOT_READY`). Expected: both exit 0.
2. As the repository owner (`James3014`; the readiness-control marker is honored only when the
   issue author equals the repository owner), create the control Issue in `James3014/Nexus-new`. Its body is a
   natural-shaped engineering task and contains this line:

   ```
   NEXUS-HYBRID-REPLICATION-READINESS-CONTROL-V1:<token>
   ```

   The capture workflow records it as `READINESS_CONTROL_EXCLUDED` and the control is never
   part of the primary cohort. Note the Issue number as `<CONTROL_KEY>`.
3. The control must reach the DM1 intercept: its sealed raw carries
   `raw_response.dm1_decision` with `applicable: true` and a choice (route A requires the
   deterministic closure receipt instead). A control that is routed to C without DM1 yields
   the blocker `CONTROL_DM1_NOT_REACHED` in step 5. Stop there and fix the control; waiving
   it (`--allow-control-without-dm1`) is an Owner-only decision, not a runbook step.

## 5. Daemon readiness run and daemon-absent negative control

host (Mac mini). Prerequisite: set `activation_state` in `<BINDING>` to
`READINESS_CONTROL_PENDING` (the `stack --readiness-control` mode requires exactly that
state) and re-run step 2. Do not change any `strong_online` pin field.

Service observation for the positive run, written from `launchctl list com.nexus.hybrid-replication`:

```
{"schema": "nexus.hybrid_replication.service_observation.v1",
 "label": "com.nexus.hybrid-replication", "loaded": true,
 "observed_at": "<RFC3339 UTC>"}
```

Readiness run:

```
uv run python scripts/ops/hybrid_replication_daemon.py \
  --root <STORE_ROOT> --since <window-start RFC3339 UTC> \
  --frozen-policy-sha256 <frozen-policy-sha256> \
  --stack-command "uv run --project <RUNTIME> python -m nexus.research.hybrid_replication_live stack --binding <BINDING> --readiness-control --store-root <STORE_ROOT>" \
  --ground-truth-command "uv run --project <RUNTIME> python -m nexus.research.hybrid_replication_live ground-truth" \
  --readiness-control-task-key <CONTROL_KEY> \
  --service-observation <observation-loaded-true.json> \
  --launchd-label com.nexus.hybrid-replication
```

`<frozen-policy-sha256>` is the frozen policy file hash
`70c86133c9dea9dcfb0f725aa13e5acdf3fb8686c69e311a5355465568d7cea8`, carried unchanged
since V1 (#1216 comments on PR #1316 activation and on 2026-10-10 G-W3-0). It is not
recomputed; a different value means the policy file drifted, so stop.

Expected: exit 0 and a final report with
`"status": "AUTOMATIC_CAPTURE_READY"`, `"blockers": []`, `"control_dm1_requirement":
"REQUIRED"`, `"control_dm1_reached": true`. Exit 6 means `NOT_READY`; read `blockers`
(`NON_VACUOUS_E2E_CONTROL_REQUIRED`, `MISSING_CAPTURE`, `MISSING_ADMISSION`,
`WATCHDOG_INCOMPLETE`, `ADVANCE_FAILURE_PRESENT`, `DAEMON_NOT_LOADED`,
`CONTROL_NOT_SCORED`, `CONTROL_SCORE_INVALID`, `CONTROL_RAW_INVALID`,
`CONTROL_RAW_FAILURE_PRESENT`, `CONTROL_DM1_NOT_REACHED`). Stop on any blocker. Exit 3, 4
or 5 (missing capture, missing admission, advance failure) are also stops.

Daemon-absent negative control: repeat the same command with an observation whose `loaded`
is `false` (the service stopped or unloaded):

```
{"schema": "nexus.hybrid_replication.service_observation.v1",
 "label": "com.nexus.hybrid-replication", "loaded": false,
 "observed_at": "<RFC3339 UTC>"}
```

Expected: exit 6, `"status": "NOT_READY"`, `DAEMON_NOT_LOADED` in `blockers`. If it exits 0
the readiness gate does not detect a missing daemon: stop and report. Reload the service
afterwards and confirm `loaded: true` before step 6.

## 6. Open the generation

host (Mac mini). The point of no return for the generation boundary.

1. Set `activation_state` in `<BINDING>` to `AUTOMATIC_CAPTURE_READY` (pin fields
   unchanged) and re-run step 2. Expected: exit 0, `activation_allowed: true`.
2. In the manifest set `activation_state: "AUTOMATIC_CAPTURE_READY"` and `t_auto` to the
   current UTC time as `YYYY-MM-DDTHH:MM:SSZ`. `parse_manifest` rejects
   `AUTOMATIC_CAPTURE_READY` with `t_auto: null`. Keep `excluded_tasks` as decided by the
   Owner (set it before opening; it is part of the boundary hash).
3. Push and read back:

```
uv run python scripts/ops/hybrid_replication_activation.py push --manifest <manifest>
uv run python scripts/ops/hybrid_replication_activation.py readback --manifest <manifest>
```

Expected: `push` exit 0; `readback` exit 0 with `"drift": []`. Stop on `readback` exit 2 and
set the state back to `NOT_READY` by pushing a manifest with `activation_state:
"NOT_READY"`. Only issues created at or after `t_auto` are admissible.

## 7. Rules while the generation is collecting

- Per-task fail-close (D2): a protocol loss on one task excludes that task
  (`PROTOCOL_EVIDENCE_ONLY_DO_NOT_COUNT`). It does not reset the generation.
  `AUTOMATION_CONTRACT.json` `fail_close.generation_reset_for_single_task_protocol_loss` is
  `false`.
- Generation reset is allowed only for `EXECUTION_IDENTITY_DRIFT` or
  `SYSTEMATIC_DEFECT_AFFECTING_ALL_TASKS` (`fail_close.generation_reset_only_for`). A reset
  means a new generation label, a new freeze (step 1) and a new run of steps 2 to 6.
- Changes to `main`, including `scripts/ops/nexus-agy-dispatch`, do not affect the frozen
  runtime. The stack and preflight read `<RUNTIME>` and the pinned dispatcher named in
  `<BINDING>`. Do not edit the worktree, the pin or the pin fields in the binding. Do not
  rebase the worktree onto `main`.
- Campaign meta-work is excluded automatically (D3): issues for `James3014/Nexus-new#1216`
  and `#1196`, and issues whose title or body contains a marker in
  `AUTOMATION_CONTRACT.json` `primary_cohort_exclusions.campaign_markers`, get the
  disposition `CAMPAIGN_META_WORK_EXCLUDED`.
- Activation variables change only through the manifest (`push`, then `readback`). Drift
  reported by `readback` (exit 2) is corrected by pushing the manifest again, never by
  editing a repository variable.

## 8. Collecting-phase daemon: parallel advance (V12, #1934)

Run the launchd daemon with `--max-concurrent-tasks 4` (default `1` = serial, unchanged):

```
uv run python scripts/ops/hybrid_replication_daemon.py \
  --root <STORE_ROOT> --since <t_auto> \
  --frozen-policy-sha256 <frozen-policy-sha256> \
  --stack-command "<same stack command, with --store-root <STORE_ROOT>>" \
  --ground-truth-command "<same ground-truth command>" \
  --max-concurrent-tasks 4
```

- Why: serial processing put a task behind other tasks' 15 to 30 minute stack calls, so
  quickly closed issues hit `TERMINAL_BEFORE_EXECUTION_START` (10 of 47 primary tasks in V11).
- With N > 1 the daemon first takes `execution_start.json` for every ADMITTED primary task
  (under a non-blocking flock on the per-task `execution.lock`; a task whose lock is held is
  already executing), then advances up to N tasks at a time. The stack subprocess reuses the
  existing `execution_start.json`. The readiness control task is never pre-fenced.
- The `execution.lock` is a `flock` on a per-open file, exclusive across threads and
  processes. Keep the launchd wrapper's `shlock` so only one daemon invocation runs.
- The advance report keeps `advanced` and `failures` and gains `excluded_protocol_loss`:
  tasks with a `prospective_protocol_loss.json` are skipped, listed there, and never produce
  exit 5. A loss first recorded during the run appears with `"newly_recorded": true`, also
  non-failing (it is a recorded D2 exclusion). Exit codes 0/3/4/5/6 are unchanged; 5 now means
  a real, non-excluded advance failure.

### 8.1 Fence-only pass (`--fence-only`)

The early fence in 8 runs only at the start of an invocation, and one invocation with a backlog
can last hours. Issues admitted meanwhile would wait. `--fence-only` closes that gap: it
ingests, takes `execution_start.json` for every ADMITTED primary task, prints a report
(`nexus.hybrid_replication.daemon_fence.v1`: `fenced`, `already_executing`, `failures`,
`excluded_protocol_loss`) and exits. It never advances a task and never calls the stack or
ground-truth commands, so neither command is required. Exit codes: 5 on a real fence failure,
else 3/4 for missing capture/admission (as `--ingest-only`), else 0.

Safety beside a running main daemon:

- The per-task fence uses a non-blocking flock on `execution.lock`. A task whose stack call is
  running holds that lock and is reported in `already_executing`.
- Ingest takes a short blocking flock on `<STORE_ROOT>/ingest.lock` (held only while ingesting,
  never across advance), so a fence-only ingest and the main daemon's start-of-run ingest
  serialize. `state.json` is published atomically (unique temp file, then link/rename), so a
  concurrent scan never sees a partial file and two writers never share a temp file.

Suggested `run.sh` (the real script lives outside the repo; adjust paths):

```
#!/bin/bash
# launchd StartInterval=60. Two independent locks.
COMMON=(--root "$STORE_ROOT" --since "$T_AUTO")

# 1. Fence pass: short, own lock, never waits behind the main daemon.
if shlock -f /tmp/hybrid-replication-fence.lock -p $$; then
  uv run python scripts/ops/hybrid_replication_daemon.py "${COMMON[@]}" --fence-only
  rm -f /tmp/hybrid-replication-fence.lock
fi

# 2. Main daemon: long-running, its own lock (as before).
if shlock -f /tmp/hybrid-replication.lock -p $$; then
  uv run python scripts/ops/hybrid_replication_daemon.py "${COMMON[@]}" \
    --frozen-policy-sha256 "$POLICY_SHA" \
    --stack-command "$STACK_COMMAND" --ground-truth-command "$GT_COMMAND" \
    --max-concurrent-tasks 4
  rm -f /tmp/hybrid-replication.lock
fi
```

Step 1 must run before step 2 in each tick and must not be gated by the main daemon's lock.
Because each launchd tick runs `run.sh` to completion, a long main daemon blocks the next tick;
to keep the fence pass running every minute, start the main daemon in the background
(`... &`) or run the fence pass from a second launchd job.
