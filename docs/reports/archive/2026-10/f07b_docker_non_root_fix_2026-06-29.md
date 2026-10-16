# F-07B Docker Non-Root Fix

**Status:** `F07B_DOCKER_NON_ROOT_FIXED`

**Date:** 2026-06-29

## Summary

Converted 5 Dockerfiles to run as non-root user `nexus`.

## Files Changed

| File | Base Image | Fix |
|---|---|---|
| `Dockerfile.swe` | `python:3.11-slim` | Added `useradd`, `chown`, `USER nexus` |
| `nexus_swarm/node/Dockerfile` | `python:3.12-slim` | Added `useradd`, `chown`, `USER nexus` |
| `nexus_swarm/manager/Dockerfile` | `alpine:3.19` | Added `addgroup`/`adduser`, `--chown`, `USER nexus` |
| `nexus-swarm-v22-prod/node/Dockerfile` | `python:3.12-slim` | Added `useradd`, `chown`, `USER nexus` |
| `nexus-swarm-v22-prod/manager/Dockerfile` | `alpine:3.19` | Added `addgroup`/`adduser`, `--chown`, `USER nexus` |

## Commands Run

```bash
rg -n "^USER|^FROM" <each Dockerfile>
```

## Results

| Dockerfile | Before | After |
|---|---|---|
| `Dockerfile.swe` | root | nexus |
| `nexus_swarm/node/Dockerfile` | root | nexus |
| `nexus_swarm/manager/Dockerfile` | root | nexus |
| `nexus-swarm-v22-prod/node/Dockerfile` | root | nexus |
| `nexus-swarm-v22-prod/manager/Dockerfile` | root | nexus |

## Scope Statement

- Only Dockerfiles modified
- No application logic changed
- No ports/entrypoints/CMD changed
