# Issue #1025 — R2 Gateway runtime convergence

artifact_authority: current
status: ACTIVE
owner: James Chen
execution_lane: GOVERNED
AUTO_CHAIN: false

## Current frontier

- Durable owner: `James3014/Nexus-new#1025`
- Desired Nexus-new: `c6e2609f9c148e42d96eaf9e1e9cfddb0579ad33`
- Desired tree: `7fd8be2eb8b20a81d9279aa7bb4400a7fdedeef6`
- Loaded Gateway: `db57b1e44715e83bd1aea1c5f81ff058b2745782`
- Loaded runtime package: `nexus-runtime@b48fbd7abe96041bffcea31fa31fa90e78582f02`
- Required runtime package: `nexus-runtime@632e1a18d164d7dadf6bb98caa9c4e9d17c436f3`
- R2-A: `SOURCE_AHEAD_OF_RUNTIME`

## Canonical mechanism

Reuse #526 durable Gateway recovery. No new recovery/process authority.

## Dependency frontier

1. Merge this Task Card/INDEX bootstrap.
2. Rebind the exact current source under this Card.
3. Converge only the fixed Gateway interpreter's `nexus-runtime` package generation and verify exact API identity.
4. Create/merge one fresh #526 recovery authority receipt for desired `c6e2609f...` over predecessor `db57b1e4...`.
5. Run typed zero-effect recovery preflight.
6. Execute the exact #526 recovery only if every preflight identity remains current.
7. Reconcile unknown outcome; never blind retry.
8. Physically read back source + package + server/tool identity.
9. Stop at R2; R3 is not auto-chained.

## Next gate

`R2_CURRENT_TARGET_REBOUND_TO_VALID_CANONICAL_MAIN`
