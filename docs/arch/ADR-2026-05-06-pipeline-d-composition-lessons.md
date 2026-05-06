# ADR: Composition phases must not retain silent legacy fallbacks

## Status

Accepted

## Context

The D-stage diagnose executor had a default composed implementation, but the
pipeline still registered `_stage_diagnose` as a legacy fallback when executor
bootstrap returned no plugins. That made the architecture look composition-first
while preserving the old mixin path under failure.

## Decision

Diagnose is now composition-only:

- Default bootstrap still registers the D executor when dependencies are valid.
- Legacy fallback registration excludes D.
- `_LegacyPhaseAdapter` no longer maps D to `_stage_diagnose`.

## Consequences

If the D executor cannot bootstrap, the pipeline no longer masks that condition
by running the old mixin stage. This makes composition failures visible and keeps
future phase extraction work honest.

## Lesson

Removing a mixin phase is not complete while a fallback can silently call it.
Each extracted phase needs a regression test that proves both the happy composed
path and the bootstrap-failure path.
