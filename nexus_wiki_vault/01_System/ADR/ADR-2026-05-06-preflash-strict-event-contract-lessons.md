---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR: Pre-Flash Strict Event Contract Lesson

Date: 2026-05-06

## Context

Adding an explicit `strict_event_contracts` seam to the pre-Flash gate changed
`validate_event_contracts()` from a positional-only test seam to a keyword-aware
contract. A monkeypatched regression test failed because its fake validator did
not accept the new keyword.

## Decision

Pre-Flash gate validators that are expected to be monkeypatched in tests must
keep keyword-compatible fake seams when optional policy arguments are added.

## Lesson

Fail-closed gate policy knobs should be explicit, but tests around those gates
must fake the public seam, not the old function shape. Otherwise the test suite
can fail on mock shape drift instead of runtime behavior.
