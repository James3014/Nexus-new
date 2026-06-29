# F-12A Sandbox Bypass Audit

**Status:** `F12A_SANDBOX_BYPASS_AUDIT`

**Date:** 2026-06-29

## Summary

Inventory of 16 sandbox/bypass flag usages across the codebase.

## Bypass Flags Found

| Flag | Files | Classification |
|---|---|---|
| `NEXUS_GATE_BYPASS` | 5 | Docs-only (4), Runtime (1) |
| `NIGHTSHIFT_BYPASS_POLICY` | 3 | Runtime (2), Test (1) |
| `NIGHTSHIFT_BYPASS_LEARN_SLO` | 4 | Runtime (2), Test (2) |
| `NEXUS_BYPASS_LEARN_SLO` | 1 | Runtime (1) |
| `--dangerously-bypass-approvals-and-sandbox` | 1 | Runtime (1) |

## Classification by Reachability

| Classification | Files | Risk |
|---|---|---|
| Docs-only | 4 | Low |
| Test-only | 3 | Low |
| Runtime reachable | 8 | High |
| Dev-tool only | 1 | Medium |

## Top Runtime-Reachable Risky Paths

| File | Flag | Risk |
|---|---|---|
| `scripts/ops/start_codex_nexus_enforced.sh` | `--dangerously-bypass-approvals-and-sandbox` | High |
| `nexus/app/nightshift_runner_service.py` | `NIGHTSHIFT_BYPASS_POLICY` | High |
| `nexus/app/nightshift_runner_service.py` | `NIGHTSHIFT_BYPASS_LEARN_SLO` | High |
| `scripts/bench/real_world_task_runner.py` | Multiple bypass flags | Medium |
| `scripts/shadow_audit_v24.sh` | `NEXUS_GATE_BYPASS` | Medium |

## Commands Run

```bash
rg -n 'NEXUS_GATE_BYPASS|NEXUS_BYPASS|NIGHTSHIFT_BYPASS|dangerously-bypass-approvals-and-sandbox|DISABLE_SANDBOX|NO_SANDBOX' nexus scripts tests nexus_swarm --glob '!docs/**' --glob '!artifacts/**'
```

## Scope Statement

- Audit only, no code changes
- Identified 8 runtime-reachable bypass paths
- Top risky path: `--dangerously-bypass-approvals-and-sandbox`
