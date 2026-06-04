# ADR 0015: v28 Architecture Freeze & Contract Sealing

## Status
Accepted

## Context
Following the v28.1 state architecture refactor, the governance platform has been decoupled into four distinct layers: State, Telemetry, Memory Retrieval, and Judgment. To prevent future boundary erosion and state drift, we must freeze the public interfaces of these core modules.

## Decision
We formally declare the following interfaces as **STABLE**. Any change to these signatures requires a version bump of the governance plane.

### 1. State Layer (`TaskStateStore`)
- `get_latest(task_id)`
- `commit(task_id, payload)`
- `rollback(task_id, to_version)`
- **Invariant**: State is the single source of truth; all other modules must read from or be injected by the state store.

### 2. Telemetry Layer (`TelemetryBundle`)
- Properties: `wall_time_ms`, `token_usage`, `provider_costs`, `overhead_ms`.
- **Invariant**: `complete` property is the prerequisite for public claim eligibility.

### 3. Retrieval Layer (`MemoryRetrievalService`)
- `rank_and_pack(hits, current_state_version)`
- **Invariant**: Causal ranking order ($Failure Signature > Family > Archive$) and physical version filtering are mandatory.

### 4. Judgment Layer (`GateJudge`)
- `decide(ticket_id, replay, telemetry, evidence_seal)`
- **Invariant**: Pure function; no internal I/O or implicit context dependency.

## Consequences
- **Decoupling**: Engineering teams can evolve execution lanes (Django, Astropy) without affecting governance core purity.
- **Auditability**: All decisions are replayable and verifiable via SHA-256 evidence seals.
- **Migration**: Legacy data must be backfilled using `BackfillService` to meet these contracts.
