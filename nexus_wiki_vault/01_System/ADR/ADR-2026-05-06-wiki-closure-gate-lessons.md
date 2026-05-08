---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

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

## Follow-up Lesson: Global Coverage Closure
Raising global wiki coverage should use a dedicated provenance index rather than
scattering shallow one-line pages across the vault. The `Source - Coverage
Heatmap` page is allowed to prove baseline traceability, but it must state that
indexed coverage is not the same as deep behavior documentation.

Full-vault linter failures can predate the current slice. When that happens,
the current changed page must still be linted directly and the pre-existing
vault debt must be reported separately instead of blocking an unrelated coverage
closure.
