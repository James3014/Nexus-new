# ADR: Audit CLI Consistency and Event Strict Mode Lessons

Date: 2026-05-06

## Context

The pre-Flash audit tools already emitted JSON, but they did not accept a shared
`--output-json` flag. This made orchestration brittle because callers had to know
per-script CLI quirks. Event contract auditing also treated raw transition
events as migration warnings, but there was no opt-in gate for promoting that
warning into a failure.

## Decision

Audit commands accept `--output-json` as a compatibility flag while preserving
their current JSON stdout behavior. `NexusEventBus.audit_event_contracts` now
supports `fail_on_raw=True`, and `nexus_pre_flash_gate.py` wires that through
`NEXUS_EVENT_RAW_STRICT=1`.

## Lesson

Promotion gates should have stable machine interfaces. If a script already
returns JSON, accepting a common JSON flag avoids false failures caused by
interface drift rather than runtime drift.
