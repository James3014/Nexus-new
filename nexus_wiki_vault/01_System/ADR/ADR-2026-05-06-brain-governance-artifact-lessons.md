---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR: Governance and coverage closure need replaceable seams and durable artifacts

## Status

Accepted

## Context

Two M5 closure checks were still too easy to overstate:

- `LearningScorer` directly called `LearningGovernance.evaluate()`, making the
  governance decision hard to replace in runtime composition or tests.
- Brain Hub coverage rendering only wrote markdown and printed a summary. The
  full code-reality payload was not persisted as an auditable artifact.

## Decision

- `LearningScorer.apply()` now accepts an optional governance evaluator seam.
- `render_brain_hub_coverage.py` can write a full JSON artifact containing both
  the coverage payload and the gate decision.

## Consequences

Governance behavior can now be injected without monkeypatching a classmethod, and
Brain Hub coverage can be archived as machine-readable evidence rather than
being inferred from a terminal summary.

## Lesson

Runtime alignment is not closed by human-readable output alone. Decisions need
replaceable seams, and audits need durable payloads that downstream gates can
read without replaying the command.
