# ADR-2026-05-06: Wiki Closure Gates Need Runtime Semantics

## Status
Accepted

## Context
The final closure review exposed two failure modes that made completed runtime
work appear unfinished:

- A missing optional product path was treated as an uncovered mandatory runtime
  key path.
- Capability audit labels existed semantically, but exact provenance values did
  not match the audit contract.

## Decision
Separate missing products from uncovered existing key paths, keep missing paths
visible in `keypath_missing`, and add exact provenance labels to the canonical
wiki pages required by the capability audit.

## Consequences
Closure gates now distinguish runtime failure from documentation coverage debt.
Future agents should not reopen the 18-item architecture list unless a runtime
test or gate fails.

## Lesson
Governance gates must encode the difference between "not present in this
checkout", "present but undocumented", and "runtime behavior missing". Collapsing
those states into a single FAIL creates churn instead of evidence.
