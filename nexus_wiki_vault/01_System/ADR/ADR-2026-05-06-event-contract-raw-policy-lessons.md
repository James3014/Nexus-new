---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR: Stage raw event contracts before strict cutover

## Status

Accepted

## Context

The event contract migration needs a fail-closed path without breaking existing pipeline traces during the transition from raw event names to semantic events. A TDD red run exposed three concrete gaps:

- `NexusEventBus.audit_event_contracts()` had no staged `raw_policy`, only a boolean strict flag.
- `nexus_pre_flash_gate.validate_event_contracts()` did not report raw warning metadata in default mode.
- `NexusPipeline` still emitted `phase_start`, `phase_end`, and `lifecycle_pre` directly from pipeline code.

## Decision

Raw event policy is now explicit:

- `warn`: default transition mode; raw events are reported as warnings but do not fail the gate.
- `block` / `strict`: raw events fail the gate.
- `allow`: compatibility mode for temporary local probes.

Pipeline phase lifecycle events now go through semantic event factory helpers:

- `build_lifecycle_hook_event()`
- `build_phase_transition_event()`

## Consequences

Pre-Flash can report raw event debt without blocking every run during the migration window. Strict mode remains available for promotion gates. New pipeline event producers should use the factory seam instead of hand-writing raw event names.

## Lesson

Do not collapse migration observability and promotion enforcement into one boolean. A staged policy preserves evidence while still giving CI a strict cutover switch.
