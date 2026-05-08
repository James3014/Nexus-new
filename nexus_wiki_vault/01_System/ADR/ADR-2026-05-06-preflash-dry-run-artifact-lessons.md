---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR: Quick pre-Flash checks must not mutate evidence directories

## Status

Accepted

## Context

The OpenSeeker/AutoData pre-Flash smoke check validated the right concepts, but
it always wrote `.nexus/reports/pre_flash_autodata_manifest.json`. That made a
quick gate look deterministic while still mutating local evidence directories.

## Decision

The smoke check now separates validation from persistence:

- `validate_openseeker_autodata_smoke()` computes an in-memory manifest summary
  by default.
- Explicit write mode persists the manifest and marks the summary as written.
- `nexus_pre_flash_gate.py --quick` stays non-mutating unless
  `--write-artifacts` is requested.

## Consequences

Agents can wear Nexus and run pre-Flash checks without creating misleading dirty
state. Artifact creation is still available when a promotion run needs durable
evidence.

## Lesson

A smoke check that mutates the evidence tree is not a pure smoke check. Promotion
artifacts should be explicit, not a side effect of asking whether the gate would
pass.
