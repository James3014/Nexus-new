# Hermes Local Controller Wave D — Host Runtime and Soak Qualification

Date: 2026-10-04
Tracking: James3014/Nexus-new#1395
Predecessor: #1392 / PR #1393
Activation ceiling: runtime qualification + bounded soak only; no 24x7 daemon

## D1 source qualification

The canonical host runtime manifest now includes:

- `scripts/ops/nexus-hermes-controller-guard`
- `scripts/ops/nexus-hermes-continuation-controller`

Both are source-linked content-addressed components. Mutable Hermes state is not
part of the runtime bundle: no session DB, OAuth state, provider credentials,
local model cache, or Hermes config is copied by host sync.

Host sync now:

1. includes both files in the bundle digest,
2. links their installed entrypoints to the active immutable generation,
3. reports their SHA-256 and entrypoint identity in `status` / `verify`,
4. removes their symlinks when rolling back to a generation that does not
   declare those components.

Dedicated rollback negative control proves:

```text
legacy generation (no Hermes runtime component)
  -> sync new Hermes generation
  -> both entrypoints VERIFIED
  -> rollback
  -> both Hermes components absent
  -> both installed Hermes symlinks absent
```

## D2 soak harness

Added `scripts/ops/nexus-hermes-soak`.

The harness:

- runs the installed continuation controller as a fresh process per cycle,
- defaults to `observe` mode,
- requires explicit `--allow-effect-canary` for execute mode,
- restricts execute mode to one cycle,
- resolves current `main` through `nexus-host-sync desired`,
- verifies the exact desired runtime bundle before each cycle,
- requires both installed Hermes runtime components to be VERIFIED,
- requires the local OpenAI-compatible model endpoint to be healthy,
- records macOS memory-pressure observation,
- reads the controller's durable cycle receipt,
- rejects WAIT/BLOCKED/RECONCILE/unknown doctor disposition during observe soak,
- keeps a durable in-progress cycle identity so process restart reuses the same
  controller run ID rather than inventing a successor attempt.

An observe-only policy with no effect handlers is provided at
`scripts/ops/nexus-hermes-soak-observe-policy.json`.

## Verification

Focused verification:

```text
tests/ops/test_nexus_host_sync.py
tests/ops/test_nexus_hermes_soak.py
tests/ops/test_nexus_hermes_continuation_controller.py
tests/ops/test_nexus_hermes_controller_guard.py
```

Result:

- 43 tests passed
- Ruff check passed on changed Python surfaces
- preview-format check passed on the new soak harness and soak tests
- `git diff --check` passed

The existing `nexus-host-sync` file still has pre-existing whole-file preview
formatter differences on main; this change does not perform unrelated mass
formatting.

## Post-merge physical gate

This source Candidate does not claim the physical Mini runtime is qualified.
After merge, #1395 remains open and requires:

1. `nexus-host-sync sync` to the exact current main,
2. readback showing both Hermes components VERIFIED,
3. installed guard/controller help + observe canaries,
4. a short restart specimen from the soak harness,
5. then the real 6-12h wall-clock observe soak.

The 6-12h gate is elapsed evidence and must not be replaced by a tight loop.
24x7 launchd activation remains a later gate.
