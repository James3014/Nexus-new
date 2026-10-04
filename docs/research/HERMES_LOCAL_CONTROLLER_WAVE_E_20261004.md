# Hermes Local Controller Wave E — Staged 24x7 Activation

Date: 2026-10-04
Owner issue: #1397
Predecessors: #1386 / #1392 / #1395
Claim ceiling: `LOCAL_SERVICE_LIFECYCLE_ONLY_NO_WORKFLOW_ACCEPTANCE_MERGE_RELEASE`

## Goal

Prepare the Mac mini to run the Hermes local continuation controller as a durable launchd service without creating a second Nexus planner, task queue, lease authority, completion authority, merge authority, or release authority.

Wave E is split deliberately:

- **E1–E3** may be implemented, merged, and physically staged before the long soak.
- **E4 activation** remains fail-closed until #1395 supplies a real 6+ hour elapsed production observe-soak receipt on the same runtime revision and bundle.

## Service ownership

`nexus-hermes-launchd` owns only two local launchd labels:

- `com.nexus.hermes-local-model`
- `com.nexus.hermes-controller`

It does not select work. The controller service reads one explicit durable target file. The target binds both `policy_path` and `policy_sha256`; a missing or byte-drifted policy fails closed. An explicit `enabled=false` target is a no-op.

The workflow authority chain remains:

```
launchd timer
    -> nexus-hermes-launchd tick
        -> exact host-runtime verification
        -> local Splash endpoint verification
        -> explicit durable target
        -> nexus-hermes-continuation-controller
            -> workflow doctor
            -> deterministic Hermes guard
            -> Nexus Core / canonical state
            -> nexus-agy-dispatch for any Agy effect
```

## Local model service

The model launchd job binds the exact resolved Splash executable and its SHA-256 in the service config.

Current qualified binary at source preparation time:

- executable: `/opt/homebrew/Cellar/splash/1.0.2/bin/splash`
- SHA-256: `6158ce6f1d4b2eb23b6568ede41cdd06f3a70f2d05a94035720bf9ada25c8fb6`
- model: `incoai/Qwen3.6-35B-A3B-Splash`
- endpoint: `http://127.0.0.1:8000/v1/models`
- context: `65536`

An unexpected Homebrew binary change fails closed until the config is deliberately requalified.

## Activation gate

`activate` requires a machine-readable `nexus.hermes_elapsed_soak_acceptance.v1` receipt.

`accept-soak` creates that receipt only when all of the following hold:

1. soak state is terminal PASS;
2. at least two observe cycles exist;
3. state/cycle run IDs agree;
4. every cycle is PASS and `mode=observe`;
5. elapsed wall-clock time between first start and last finish is at least 6 hours;
6. every cycle observed the same current host-runtime revision and bundle;
7. every cycle had doctor `SAFE`;
8. every cycle had local model `HEALTHY`;
9. all controller states have `effects_started=0`;
10. the installed runtime at acceptance time is still the exact same revision/bundle.

Tight-loop cycles cannot satisfy the elapsed gate. Activation also re-hashes the accepted soak state/cycle receipt index; any post-acceptance receipt byte drift fails closed.

## Staged install

`stage`:

- verifies the exact Splash binary hash;
- writes both LaunchAgent plists;
- sets both labels disabled;
- never bootstraps either service;
- does not require or consume the activation receipt.

A manual staged canary uses `tick --allow-staged` and is restricted to an observe-mode target.

Production service state is kept separate from staged-canary state so an observe canary cannot contaminate the production execution epoch.

## Stable effect identity

For each explicit target hash, the service allocates a stable controller run identity:

`hermes-service-<target-hash>-e<epoch>`

Repeated launchd ticks reuse that identity while the epoch is active. Therefore controller-level effect intent, operation ID, effect budget, and no-blind-retry state survive fresh process invocations.

Changing the target while an epoch is active fails closed.

## Model takeover rule

Activation refuses to bootstrap the model launchd service when the configured endpoint is already healthy but the model label is not loaded. This prevents silently taking over an unmanaged/manual Splash process.

The existing manually started Splash process may be used for E3 staged observe canaries. Before E4 activation, it must be deliberately stopped so launchd can become the sole model-process owner.

## Health/readback

`status` reports:

- controller/model plist presence;
- launchd loaded/running/last-exit state;
- launchd disabled state;
- current service state/epoch/run identity;
- current-main host-runtime verification;
- Hermes guard/controller/launchd component verification;
- exact Splash binary hash;
- model endpoint health.

## Rollback

`disable` stops controller first, then model, and disables both labels.

`uninstall` performs the same stop/disable sequence and then removes the two plists.

The launchd manager itself is content-addressed by `nexus-host-sync`; host-runtime rollback restores/removes the installed `nexus-hermes-launchd` entrypoint with the rest of the generation.

## Source verification

Focused pre-merge suite:

- `tests/ops/test_nexus_hermes_launchd.py`
- `tests/architecture/test_effect_owner_uniqueness.py`
- `tests/ops/test_nexus_host_sync.py`

Result: 34 passed.

Ruff check, preview formatter check, and `git diff --check`: PASS.

## Remaining before E4

- merge Wave E source;
- sync exact merged main to the Mac mini host runtime;
- install production LaunchAgents in disabled/staged state;
- run manual staged observe canary and rollback/readback;
- later, run the real #1395 6–12 hour elapsed observe soak;
- accept the soak receipt;
- stop the unmanaged/manual Splash process;
- enable model + controller launchd services;
- perform reboot/resume acceptance;
- verify no duplicate effect, no second writer, and exact current-main runtime after reboot.

Until those final steps, 24x7 activation is not claimed.
