# ADR: Tenant labels are not tenant isolation

## Status

Accepted

## Context

The memory router returned a `tenant` field in responses, but its search paths did not prove that reads were scoped to that tenant. The TDD red run exposed three gaps:

- `MemPalace` had tenant-aware ingest but no tenant-scoped read seam.
- `SkillsRouter` could not receive an injected `MemPalace`.
- Palace and semantic search could return mixed-tenant or missing-tenant rows.

## Decision

Read paths now fail closed at the service/router seam:

- `MemPalace.retrieve_from_shards()` uses `storage.scoped_access(tenant_id)` and returns no rows without a tenant.
- `SkillsRouter` accepts an injected `MemPalace` and uses it for palace search when available.
- Router palace and semantic results are filtered by tenant metadata before returning results.

## Consequences

This closes the immediate cross-tenant read path without changing the storage backend or repository APIs. A later deeper refactor should push tenant predicates into the repository/retriever layer instead of relying only on router filtering.

## Lesson

A response label is not an isolation boundary. Tenant identity must constrain the read path before results can influence routing.
