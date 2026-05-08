---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR-2026-05-06 Event Contract Gate Lessons

## Context

During P330-P340, the pre-Flash event contract gate initially read the repository event log as-is and failed on a historical `test_event` record. The gate was structurally correct but too sensitive to diagnostic/test records already present in `.nexus/events/event_log.jsonl`.

## Lesson

Hard gates that audit runtime logs must distinguish production event-contract drift from diagnostic or test events. Otherwise, the gate can block promotion because of historical test residue rather than current runtime behavior.

## Decision

`NexusEventBus.audit_event_contracts()` now treats explicit diagnostic events (`test_event`, `persist_event`) as known raw transition events, while still failing on truly unknown event types.

## Verification

`uv run pytest -q tests/ops/test_nexus_pre_flash_gate.py tests/core/test_event_bus.py`
