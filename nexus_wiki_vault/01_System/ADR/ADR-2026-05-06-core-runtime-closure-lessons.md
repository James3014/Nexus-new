---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR: Core closure requires visible failures, not silent compatibility

## Status

Accepted

## Context

The remaining closure checks exposed three compatibility paths that could hide
runtime drift:

- P/X/D phase executor bootstrap could still fall back to legacy mixin methods.
- Production ContextHub strict dependency injection was configured, but there
  was no runtime marker for tests to assert.
- Learning governance event emission failures were swallowed without a receipt.

## Decision

- P/X/D are composition-only at plugin registration time.
- ContextHub records whether strict dependency mode is active.
- LearningGovernance records event emission success or failure in state metadata.

## Consequences

Bootstrap and event failures now become observable. This keeps route and
governance gates from passing through hidden compatibility paths.

## Lesson

Backward compatibility is useful only when it is explicit. Silent fallbacks make
architecture drift look like successful execution.
