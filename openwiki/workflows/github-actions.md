---
type: Concept
title: GitHub Actions Workflows & Operational Lanes
description: Inventory and operational classification of all 12 GitHub Actions workflows, distinguishing scheduled triggers, dispatches, and event hooks.
tags: [workflows, github-actions, ci-cd, operational-lanes]
openwiki:
  roles: [architecture, operations, testing]
  change_kinds: [public-api, workflow]
  source_paths: [.github/workflows/openwiki-update.yml, .github/workflows/benchmark-ci.yml, .github/workflows/pytest.yml]
  symbols: [workflow_dispatch, schedule, push, pull_request]
  test_paths: [tests/test_script_entrypoints.py]
  invariants: [Workflows are manual-only unless physically containing schedule, push, pull_request, or issues triggers.]
  validation_commands: [pytest tests/test_script_entrypoints.py -q]
---

# GitHub Actions Workflows & Operational Lanes

The repository contains 12 GitHub Actions workflow definitions under `.github/workflows/`. In accordance with the **Workflow Trigger Truth** rule, trigger modes are strictly derived from exact `on:` key declarations in source YAML files.

---

## 📋 Complete Workflow Trigger Inventory

| Workflow File | Display Name | Trigger Keys (`on:`) | Operational Mode | Target Job / Commands |
| :--- | :--- | :--- | :--- | :--- |
| `benchmark-ci.yml` | 📊 Nexus Benchmark CI | `schedule` (`0 18 * * *`), `workflow_dispatch` | Scheduled & Manual | Runs SWE-bench subset benchmarks |
| `graph-impact.yml` | Graph Impact Audit | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Evaluates dependency graph changes |
| `lint.yml` | Linting & Formatting | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Runs `ruff check` on Python files |
| `nexus-autofix.yml` | Nexus Auto-Repair | `issues` (`labeled`) | Event-driven (Issue Label) | Triggered when issue label contains `nexus:` |
| `nexus-smoke.yml` | Nexus Smoke Tests | `schedule` (`0 2 * * *`), `workflow_dispatch` | Scheduled & Manual | Nightly smoke execution suite |
| `nightshift.yml` | Nightshift Convergence | `schedule` (`0 2 * * *`), `workflow_dispatch` | Scheduled & Manual | Nightly background convergence loop |
| `openwiki-update.yml` | OpenWiki Manual Update | `workflow_dispatch` | Manual-Only | Executes OpenWiki update workflow |
| `policy-lane-gate.yml` | Policy Lane Gate | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Validates policy gate contracts |
| `pytest.yml` | Pytest Collection Gate | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Executes `pytest -q` collection gate |
| `security.yml` | Security Audit | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Runs Bandit security scanning |
| `typecheck.yml` | Pyright Typecheck | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Runs Pyright static type checker |
| `wiki-governance.yml` | Wiki Governance Gate | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Enforces wiki structure boundaries |

---

## 🏷️ Required V3 Classifications

```yaml
component: OpenWikiUpdateWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - LOCAL_RUNTIME
authority_roles:
  - DERIVED_ONLY
evidence_basis:
  - .github/workflows/openwiki-update.yml:on.workflow_dispatch
claim_ceiling: Manual-only workflow triggering OpenWiki documentation updates; holds derived observation status.
```

```yaml
component: BenchmarkCIWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - BENCHMARK
authority_roles:
  - NONE
evidence_basis:
  - .github/workflows/benchmark-ci.yml:on.schedule
claim_ceiling: Daily scheduled benchmark workflow executing SWE-bench evaluation cases.
```

```yaml
component: PytestCIWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - TEST
authority_roles:
  - GOVERNANCE_AUTHORITY
evidence_basis:
  - .github/workflows/pytest.yml:on.push
claim_ceiling: Continuous integration workflow enforcing Pytest collection and test suite verification gates.
```

---

## 🧭 Change Navigation & Validation

### When to Consult
Consult this page when modifying CI/CD pipelines, adding workflow triggers, or updating GitHub Actions job steps.

### Runtime Invariants
- A workflow is manual-only if its `on:` section contains only `workflow_dispatch`. Do not describe manual workflows as scheduled.

### Exact Source Files
- `.github/workflows/openwiki-update.yml`
- `.github/workflows/benchmark-ci.yml`
- `.github/workflows/pytest.yml`

### Focused Tests
- `tests/test_script_entrypoints.py`

### Minimal Validation Command
```bash
pytest tests/test_script_entrypoints.py -q
```
