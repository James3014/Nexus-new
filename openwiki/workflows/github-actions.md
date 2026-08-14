---
type: Concept
title: GitHub Actions Workflows & Operational Lanes
description: Current inventory and trigger classification of all 10 GitHub Actions workflows, including exact-base Pytest impact selection and trusted deletion-evidence bootstrap.
tags: [workflows, github-actions, ci-cd, operational-lanes]
openwiki:
  roles: [architecture, operations, testing]
  change_kinds: [public-api, workflow]
  source_paths: [.github/workflows/openwiki-update.yml, .github/workflows/benchmark-ci.yml, .github/workflows/pytest.yml, .github/workflows/trusted-deletion-anchor.yml]
  symbols: [workflow_dispatch, schedule, push, pull_request, pull_request_target]
  test_paths: [tests/ops/test_openwiki_source_contract.py, tests/ops/test_trusted_deletion_anchor.py, tests/ops/test_pr_impact_gate.py]
  invariants: [Workflow display names and trigger modes come from current YAML. workflow_dispatch alone is manual-only. GitHub Actions run on the CI surface and do not independently grant merge or release authority.]
  validation_commands: [pytest tests/ops/test_openwiki_source_contract.py tests/ops/test_trusted_deletion_anchor.py tests/ops/test_pr_impact_gate.py -q]
---

# GitHub Actions Workflows & Operational Lanes

The repository currently contains **all 10 GitHub Actions workflows** under `.github/workflows/`. Display names and trigger modes below are derived from the physical YAML at the synchronized GitHub revision; they are not inferred from filenames or historical workflow intent.

---

## 📋 Complete Workflow Trigger Inventory

| Workflow File | Display Name | Trigger Keys (`on:`) | Operational Mode | Current Role |
| :--- | :--- | :--- | :--- | :--- |
| `benchmark-ci.yml` | 📊 Nexus Benchmark CI | `schedule` (`0 18 * * *`), `workflow_dispatch` | Scheduled & Manual | Scheduled/manual benchmark evaluation |
| `lint.yml` | Nexus Exact-Base Ruff CI | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Exact-base Ruff/static lint lane |
| `nexus-smoke.yml` | Nexus Smoke Benchmark | `push` (`main`, `master`), `schedule` (`0 2 * * *`), `workflow_dispatch` | Scheduled, Event-driven & Manual | Protected-branch/nightly smoke benchmark |
| `openwiki-update.yml` | OpenWiki Manual Update | `workflow_dispatch` | Manual-Only | Pinned OpenWiki generation with containment checks and artifact upload |
| `policy-lane-gate.yml` | Policy Lane Gate CI | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Policy-contract validation lane |
| `pytest.yml` | Nexus Pytest CI | `push`, `pull_request`, `workflow_dispatch`, `schedule` (`17 3 * * *`) | Scheduled, Event-driven & Manual | Exact-base impact gate followed by revision-bound Pytest verification |
| `security.yml` | Nexus Exact-Base Bandit CI | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Exact-base Bandit security scan |
| `trusted-deletion-anchor.yml` | Trusted deletion-evidence bootstrap anchor | `pull_request_target` (`opened`, `synchronize`, `reopened`, `ready_for_review`) | Event-driven | Trusted controller → unprivileged executor → trusted verification path for deletion evidence |
| `typecheck.yml` | Nexus Exact-Base Pyright CI | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Exact-base Pyright type-check lane |
| `wiki-governance.yml` | Wiki Exact-Base Governance CI | `push`, `pull_request`, `workflow_dispatch` | Event-driven & Manual | Governed-Wiki structure/boundary verification |

---

## 🧪 Pytest Exact-Base Impact Gate

`pytest.yml` now starts non-manual/non-scheduled event handling with an `impact-gate` job. The workflow:

1. checks out the exact PR head / event head with full history;
2. removes checkout credentials from the working repository configuration;
3. resolves exact base/head SHA identity;
4. runs repository impact/test-selection logic;
5. carries that evidence into downstream Pytest verification.

This makes the CI claim revision-bound. A green run on another base/head pair is not evidence for the current Candidate.

---

## 🛡️ Trusted Deletion-Evidence Anchor

`trusted-deletion-anchor.yml` uses `pull_request_target` and an explicit trust split. Current source includes a trusted controller running from the default-branch workflow revision, an unprivileged executor, and trusted verification.

The trusted controller checks the repository/default branch/workflow identity, fetches the exact trusted workflow SHA into a bare repository, validates source/blob identity, builds a fixed runtime bundle, and publishes hashed controller artifacts. This lane is specialized evidence/bootstrap infrastructure; it should not be generalized into arbitrary privileged PR code execution.

---

## 📚 OpenWiki Manual Update

`openwiki-update.yml` remains manual-only because its only trigger is `workflow_dispatch`.

It installs pinned `openwiki@0.3.1`, runs `openwiki code --update --print`, restores controlled repository files, rejects any governed-Wiki mutation, rejects changes outside `openwiki/`, and uploads the generated OpenWiki directory as an artifact. Generation failure is propagated after containment checks.

The workflow provides a CI maintenance surface for derived documentation; it does not make OpenWiki a runtime or governance authority.

---

## 🏷️ Required V3 Classifications

```yaml
component: OpenWikiUpdateWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - CI
authority_roles:
  - DERIVED_ONLY
evidence_basis:
  - .github/workflows/openwiki-update.yml:on.workflow_dispatch
claim_ceiling: Manual-only CI workflow that regenerates and contains derived OpenWiki output; it holds no runtime, route, approval, integration, or release authority.
```

```yaml
component: PytestCIWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - CI
authority_roles:
  - NONE
evidence_basis:
  - .github/workflows/pytest.yml:on.push
  - .github/workflows/pytest.yml:on.pull_request
  - .github/workflows/pytest.yml:jobs.impact-gate
claim_ceiling: Revision-bound CI verification surface with an exact-base impact gate; passing CI is evidence, not merge/release authority.
```

```yaml
component: TrustedDeletionAnchorWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - CI
authority_roles:
  - GOVERNANCE_AUTHORITY
evidence_basis:
  - .github/workflows/trusted-deletion-anchor.yml:on.pull_request_target
  - .github/workflows/trusted-deletion-anchor.yml:jobs.trusted-controller
claim_ceiling: Specialized trusted/unprivileged/trusted deletion-evidence bootstrap and verification lane on pull_request_target; its authority is bounded to that governed evidence contract.
```

```yaml
component: BenchmarkCIWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - CI
  - BENCHMARK
authority_roles:
  - NONE
evidence_basis:
  - .github/workflows/benchmark-ci.yml:on.schedule
  - .github/workflows/benchmark-ci.yml:on.workflow_dispatch
claim_ceiling: Scheduled/manual benchmark CI surface; benchmark results are not product-runtime proof without separate current runtime evidence.
```

---

## 🧭 Change Navigation & Validation

### When to Consult
Consult this page when changing workflow triggers, exact-base selection, trusted PR evidence handling, OpenWiki generation, benchmark scheduling, or CI gate behavior.

### Workflow Invariants
- Copy top-level workflow `name:` values verbatim from YAML.
- `workflow_dispatch` alone means manual-only.
- Describe a workflow as scheduled only when `schedule:` exists physically.
- Treat GitHub Actions execution as `CI`; add `BENCHMARK` only when the workflow is actually a benchmark surface.
- A CI success result does not independently grant merge, integration, release, or public-claim authority.

### Exact Source Files
- `.github/workflows/openwiki-update.yml`
- `.github/workflows/pytest.yml`
- `.github/workflows/trusted-deletion-anchor.yml`
- `.github/workflows/benchmark-ci.yml`

### Focused Tests
- `tests/ops/test_openwiki_source_contract.py`
- `tests/ops/test_trusted_deletion_anchor.py`
- `tests/ops/test_pr_impact_gate.py`

### Minimal Validation Command
```bash
pytest tests/ops/test_openwiki_source_contract.py tests/ops/test_trusted_deletion_anchor.py tests/ops/test_pr_impact_gate.py -q
```
