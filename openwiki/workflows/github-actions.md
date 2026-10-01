---
type: Concept
title: GitHub Actions Workflows & Operational Lanes
description: Current inventory and trigger classification of all 13 GitHub Actions workflows, including Fast Start v2 shadow/invalidation/reconciliation lanes, exact-base Pytest impact selection, G2 published-history audit, and trusted deletion-evidence bootstrap.
tags: [workflows, github-actions, ci-cd, operational-lanes]
openwiki:
  roles: [architecture, operations, testing]
  change_kinds: [public-api, workflow]
  source_paths: [.github/workflows/openwiki-update.yml, .github/workflows/benchmark-ci.yml, .github/workflows/pytest.yml]
  symbols: [workflow_dispatch, schedule, push, pull_request, pull_request_target, issues, issue_comment]
  test_paths: [tests/ops/test_openwiki_source_contract.py, tests/ops/test_trusted_deletion_anchor.py, tests/ops/test_pr_impact_gate.py, tests/ops/test_fast_start_v2.py]
  invariants: [Workflow display names and trigger modes come from current YAML. workflow_dispatch alone is manual-only. GitHub Actions run on the CI surface and do not independently grant merge or release authority. Fast Start v2 invalidation hints are non-authoritative; canonical advisory-cache mutation is limited to the trusted default-branch reconciler with revision/hash fencing.]
  validation_commands: [pytest tests/ops/test_openwiki_source_contract.py tests/ops/test_trusted_deletion_anchor.py tests/ops/test_pr_impact_gate.py tests/ops/test_fast_start_v2.py -q]
---

# GitHub Actions Workflows & Operational Lanes

The repository currently contains **all 13 GitHub Actions workflows** under `.github/workflows/`. Display names and trigger modes below are derived from the physical YAML at the synchronized GitHub revision; they are not inferred from filenames or historical workflow intent.

---

## 📋 Complete Workflow Trigger Inventory

| Workflow File | Display Name | Trigger Keys (`on:`) | Operational Mode | Current Role |
| :--- | :--- | :--- | :--- | :--- |
| `benchmark-ci.yml` | 📊 Nexus Benchmark CI | `schedule` (`0 18 * * *`), `workflow_dispatch` | Scheduled & Manual | Scheduled/manual benchmark evaluation |
| `fast-start-v2-invalidator.yml` | Fast Start v2 Invalidator | `push` (`main`), `pull_request_target`, `issues`, `issue_comment`, `schedule` (`17 * * * *`), `workflow_dispatch` | Scheduled, Event-driven & Manual | Trusted-default-branch Fast Start wakeup hints plus fenced canonical advisory-cache reconciliation |
| `fast-start-v2-shadow.yml` | Fast Start v2 Shadow | `pull_request`, `workflow_dispatch` | Event-driven & Manual | Read-only deterministic/live shadow proof for Fast Start v2 |
| `git-history-secret-audit.yml` | Git History Secret Audit | `pull_request`, `workflow_dispatch` | Event-driven & Manual | G2 full published-ref secret-history evidence runner; least privilege and no merge/release authority |
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

## ⚡ Fast Start v2 Shadow, Invalidator & Reconciler

`fast-start-v2-shadow.yml` is a read-only Candidate/shadow lane. It runs deterministic Fast Start tests and a live frontier projection without writing Issue #549.

`fast-start-v2-invalidator.yml` remains the trusted-default-branch event lane. Its `pull_request_target` path checks out trusted `main`, not untrusted PR-head code. The `invalidator` job derives bounded impact hints from GitHub metadata/changed paths and may append only `WAKEUP_HINT_ONLY` receipts to #549. Those hints never grant readiness, dispatch, claim, approval, merge, runtime, release, or production authority.

The same workflow now owns the single GitHub-side canonical advisory-cache reconciler. The `reconciler` job runs on relevant events, hourly `schedule`, and `workflow_dispatch`; it re-reads #549 plus current GitHub authority, uses metadata-only blocker reads for blocked entries, and refuses implementation source/test bodies, PR diffs, or patches on those paths. Current-main movement is wakeup evidence only. With no material semantic entry change it performs `NOOP`; with a proven material change it may update only #549, increment the registry revision once, recompute the payload hash, enforce a pre-write body/revision/hash fence, and verify post-write readback.

Neither Fast Start workflow selects a route/worker, dispatches work, approves/merges a Candidate, or grants runtime/release/production authority.

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
component: FastStartV2InvalidatorWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - CI
authority_roles:
  - DERIVED_ONLY
evidence_basis:
  - .github/workflows/fast-start-v2-invalidator.yml:on.push
  - .github/workflows/fast-start-v2-invalidator.yml:on.pull_request_target
  - .github/workflows/fast-start-v2-invalidator.yml:on.issues
  - .github/workflows/fast-start-v2-invalidator.yml:on.issue_comment
  - .github/workflows/fast-start-v2-invalidator.yml:on.schedule
  - .github/workflows/fast-start-v2-invalidator.yml:on.workflow_dispatch
  - .github/workflows/fast-start-v2-invalidator.yml:jobs.reconciler
claim_ceiling: Non-authoritative wakeup projection plus fenced mutation of the ADVISORY_CACHE_ONLY registry #549. It cannot mutate product Issue authority or grant execution authority.
```

```yaml
component: FastStartV2ShadowWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - CI
authority_roles:
  - NONE
evidence_basis:
  - .github/workflows/fast-start-v2-shadow.yml:on.pull_request
  - .github/workflows/fast-start-v2-shadow.yml:on.workflow_dispatch
claim_ceiling: Read-only deterministic/live Fast Start validation surface; passing shadow evidence is not merge, runtime, or dispatch authority.
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
Consult this page when changing workflow triggers, Fast Start invalidation/shadow/reconciliation behavior, exact-base selection, trusted PR evidence handling, OpenWiki generation, benchmark scheduling, or CI gate behavior.

### Workflow Invariants
- Copy top-level workflow `name:` values verbatim from YAML.
- `workflow_dispatch` alone means manual-only.
- Describe a workflow as scheduled only when `schedule:` exists physically.
- Treat GitHub Actions execution as `CI`; add `BENCHMARK` only when the workflow is actually a benchmark surface.
- Fast Start invalidation hints are non-authoritative; only the trusted default-branch reconciler may mutate the sole `ADVISORY_CACHE_ONLY` registry, and only behind revision/hash fencing.
- A CI success result does not independently grant merge, integration, release, or public-claim authority.

### Exact Source Files
- `.github/workflows/fast-start-v2-invalidator.yml`
- `.github/workflows/fast-start-v2-shadow.yml`
- `.github/workflows/git-history-secret-audit.yml`
- `.github/workflows/openwiki-update.yml`
- `.github/workflows/pytest.yml`
- `.github/workflows/trusted-deletion-anchor.yml`
- `.github/workflows/benchmark-ci.yml`

### Focused Tests
- `tests/ops/test_fast_start_v2.py`
- `tests/ops/test_openwiki_source_contract.py`
- `tests/ops/test_trusted_deletion_anchor.py`
- `tests/ops/test_pr_impact_gate.py`

### Minimal Validation Command
```bash
pytest tests/ops/test_fast_start_v2.py tests/ops/test_openwiki_source_contract.py tests/ops/test_trusted_deletion_anchor.py tests/ops/test_pr_impact_gate.py -q
```
