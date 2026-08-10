---
type: Concept
title: OpenWiki Entrypoint & Task-Routing Quickstart
description: Derived navigation for the Nexus repository; current authority lives in AGENTS.md and executable contracts.
tags: [quickstart, overview, navigation, openwiki]
openwiki:
  roles: [architecture, domain]
  change_kinds: [public-api]
  source_paths: [scripts/engine/nexus_cli.py, nexus/engine/capability_planner.py]
  symbols: [nexus, CapabilityPlanner]
  test_paths: [tests/ops/test_codex_task_context_index.py]
  invariants: [CapabilityPlanner is sole route authority. OpenWiki is derived_non_authoritative.]
  validation_commands: [python3 -m pytest -q tests/ops/test_codex_task_context_index.py]
---

# OpenWiki quickstart

OpenWiki is a repository-derived observation and navigation layer. It is
`derived_non_authoritative`: `AGENTS.md`, task cards, and executable contracts
remain authoritative. OpenWiki cannot create, infer, promote, or duplicate
route, governance, approval, lifecycle, or release authority.

## Start with canonical developer surfaces

- [Repository README](../README.md): portable core/provider setup split and the
  test command matrix.
- [Contributing guide](../CONTRIBUTING.md): bounded change and evidence rules.
- [Testing runbook](../docs/testing/test_runbook.md): current verification
  commands and claim ceilings.
- [Codex context index](../configs/codex_task_context_index.json): bounded,
  non-authoritative task retrieval map.

The context index is validated by:

```bash
python3 scripts/ops/validate_codex_context_index.py configs/codex_task_context_index.json
```

It covers five task classes and is limited to four context files / 16,000 bytes
per class and 8,000 bytes overall.

## Architecture pointers

The source observations below are navigation aids only; verify every claim
against current source and tests:

- [Capability planner](routing/capability-planner.md) — `CapabilityPlanner` and
  `HybridRouteDecision` remain route authorities.
- [CLI and cueline](runtime/cli-and-cueline.md) — the primary CLI source is
  `scripts/engine/nexus_cli.py`.
- [Validation suites](testing/validation-and-benchmarks.md) — use the current
  `scripts/ops/test_repo.sh` modes and the bounded fixture smoke.

## Authority ceiling

This page does not replace repository policy, select providers or models, run
lifecycle transitions, or establish benchmark, release, or production truth.
