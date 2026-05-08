---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR: Composed Audit Accepted Path Lesson

Date: 2026-05-06

## Context

A regression test for the composed A phase accepted path showed that
`_run_composition_audit_phase()` returned `None` after an `APPROVED` composed
audit. The caller interpreted `None` as "no composed audit result" and fell
through to the legacy audit path.

## Decision

A composed audit executor must return an explicit accepted audit result when it
approves, not only when it rejects.

## Lesson

Composition seams must return explicit positive and negative outcomes. Returning
`None` for success makes success indistinguishable from "plugin absent" and can
silently bypass the new runtime path.
