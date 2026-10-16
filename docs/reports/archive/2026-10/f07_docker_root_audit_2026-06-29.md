# F-07A Docker Root Audit

**Status:** `F07A_DOCKER_ROOT_AUDIT`

**Date:** 2026-06-29

## Summary

Audited 7 Dockerfiles. 5 run as root, 1 already non-root, 1 external.

## Audit Results

| Dockerfile | USER Directive | Runs as Root? | Fix Difficulty |
|---|---|---|---|
| `./Dockerfile` | `nexus` (line 51) | No | N/A |
| `./Dockerfile.swe` | None | Yes | Low |
| `./nexus_swarm/manager/Dockerfile` | None | Yes | Low |
| `./nexus_swarm/node/Dockerfile` | None | Yes | Low |
| `./nexus-swarm-v22-prod/manager/Dockerfile` | None | Yes | Low |
| `./nexus-swarm-v22-prod/node/Dockerfile` | None | Yes | Low |
| `./artifacts/external_sources/sympy_13852/doc/Dockerfile.htmldoc` | N/A | N/A | External (skip) |

## Recommended Fix Order

1. `./Dockerfile.swe` — Simple, no privileged paths
2. `./nexus_swarm/node/Dockerfile` — Simple Python app
3. `./nexus-swarm-v22-prod/node/Dockerfile` — Same as above
4. `./nexus_swarm/manager/Dockerfile` — Go binary, needs user creation
5. `./nexus-swarm-v22-prod/manager/Dockerfile` — Same as above

## Fix Template

For each Dockerfile, add before `CMD`:
```dockerfile
RUN addgroup -S nexus && adduser -S nexus -G nexus
USER nexus
```

## Commands Run

```bash
find . -name "Dockerfile*" -type f
rg -n "^FROM|^USER|chmod|chown|EXPOSE|ENTRYPOINT|CMD" <each>
```

## Scope Statement

- Audit only, no Dockerfiles modified
- Identified 5 files needing non-root fix
