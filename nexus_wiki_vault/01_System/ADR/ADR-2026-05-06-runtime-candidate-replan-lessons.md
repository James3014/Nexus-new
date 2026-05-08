---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR-2026-05-06: Runtime Candidate Replan Lessons

## Status
Accepted

## Context
Autoreason is fail-closed unless routing explicitly selects it. A route can initially estimate only one candidate, then Hyper Sprint can produce multiple candidate summaries at runtime.

## Decision
When runtime candidate summaries prove that A/B/AB judging is possible, refresh the capability plan from the observed candidate factory evidence before building autoreason receipts.

## Lesson
Fail-closed executor controls must still allow evidence-driven replanning. Static route estimates are not authoritative after runtime evidence changes the available action set.
