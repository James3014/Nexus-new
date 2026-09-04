# TASK-CORE-V1-TG2-PYTHON-PROFILE — Deterministic isolated Python verifier

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#766`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
- **Source groups:** TG-2 Python profile
- **Requirements:** REQ-007
- **Acceptance:** AC-004
- **Auto-chain:** `false`
- **Maximum claim:** `PYTHON_PROFILE_VERIFIED`
- **Depends on:** TASK-CORE-V1-TG0-FREEZE-RECONCILE
- **Dependency unlock evidence:** TG-0 accepted receipt
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

Implement the digest-pinned `python-oci-pytest-v1` clean deterministic witness profile and bind every result to source, environment, command, attempt, and artifact.

## Observable outcome

clean deterministic witness bundle

## Non-goals

No arbitrary host execution, network dependency, mutation, model invocation, trust ingestion, approval, or Stable claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-006 | contract binding | versioned Acceptance Contract and Verification Plan bind exact ChangeSet |
| REQ-007 | runner behavior | isolated exact-head deterministic Python witnesses with adequate oracle |
| AC-003 | compatibility witness | protocol/schema/contract/plan mismatch cannot certify |
| AC-004 | oracle witness | adequate pass/fail map to VERIFIED/FAILED; inadequate/unknown map UNVERIFIABLE |

## Owner decisions

DEC-003; DEC-008. OCI digest, offline lock, shell-free argv, limits, JUnit oracle, and two matching fresh runs are required.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-0 accepted receipt and Candidate source in the exact controller-bound starting HEAD/tree plus a clean isolated worker environment; this card's `Parallel safe: false` forbids auto-start but the separate Owner/controller contract permits concurrent TG-1/TG-2 dispatch as distinct Ready Issues
- **Freshness rule:** re-read contract, source digest, image digest, lock, environment, and runner availability before each certification attempt

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #766
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** one bounded Luna attempt on an issue-specific isolated worktree per exact contract/source/environment; retries use a new attempt and require matching fresh executions
- **Reconnect reconciliation:** controller re-reads the same worker/session, filesystem, Git, provider, OCI, and attempt state before retry; unknown effect is `UNVERIFIABLE`
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane in an isolated worktree
- **Verification authority:** independent controller and adequate oracle receipt; worker PASS is not acceptance
- **Receipt authority:** Completion Core after trusted ingestion
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/execution/__init__.py;product/evidence/ingestion.py;product/verification/__init__.py;tests/product/test_kernel.py;tests/product/test_trusted_evidence_ingestion.py;uv.lock
- **Edit:** product/execution/__init__.py
- **Create:** product/execution/python_runner.py;product/execution/profiles/python-oci-pytest-v1.json;product/execution/profiles/python-oci-pytest-v1.lock;tests/product/test_python_runner.py
- **Delete:** none
- **Maximum touched production files:** 4
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** current execution namespace contains pure ports; Docker 28.5.1 is available to the controller; local base image is `python:3.12-alpine@sha256:d09d15e60962ca365d1cd544a48773bac9d33f2fb1b00f2aa0deec78ade7dc31`; current `uv.lock` SHA-256 is `3e753af334885a2f434a94d40fc8860abd151516950e7f1e3647971f2e0dfc51`; no clean OCI runner is yet verified.
- **Assumptions requiring verification:** OCI runtime, locked dependency source, JUnit adequacy, shell-free invocation, limits, and environment reproducibility.
- **Architecture risks:** host runner or weak oracle could be mistaken for certification.
- **Evidence risks:** one run or exit code cannot prove determinism.
- **Missing owner decision:** none

## Mandatory source audit

Audit execution ports, evidence bindings, contract/plan schemas, current test oracle assumptions, and the exact profile constraints before implementation.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Truth table must include adequate pass/fail, inadequate oracle, unavailable runner, nondeterminism, source/environment mismatch, and artifact replay; every unknown path remains UNVERIFIABLE.

## Implementation constraints

Use the bound digest-pinned OCI base and an explicit offline profile lock contract, shell-free argv, network disabled, read-only root/source where applicable, resource/time limits, adequate JUnit oracle, two matching fresh executions, deterministic artifact hashing, and replay protection. Never edit Evidence Trust in this card or convert unavailable, inadequate, nondeterministic, or unknown outcomes to success.

## GREEN and regression gates

AC-003 and AC-004 pass only with exact contract/version/source/environment binding and the complete oracle truth table.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG2-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_python_runner.py tests/product/test_kernel.py tests/product/test_trusted_evidence_ingestion.py` | runner truth-table and binding regression | all tests pass |
| TG2-02 | TARGET_ROOT | `uv run pytest --collect-only -q tests/product/test_python_runner.py` | prove dedicated runner tests are discovered | exit 0 with intended tests listed |
| TG2-03 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture profile/image/lock digests, exact OCI runtime/version, run and attempt IDs, source/environment/shell-free argv/stdout/stderr/exit/JUnit/artifact hashes, isolation and limits, two-run comparison, replay negative, Candidate commit, and controller live-Docker receipt.

## Independent review

Fresh reviewer validates isolation, oracle adequacy, determinism, exact bindings, negative controls, and no host/network escape.

## Exit conditions

- **PASS:** Candidate and isolated matrix support `PYTHON_PROFILE_VERIFIED`.
- **BLOCK:** inadequate oracle, unavailable/unclean runner, nondeterminism, or missing binding.
- **Residual debt:** trusted ingestion and runtime remain downstream.
- **Next gate:** after TG-1 and TG-2 independently pass, the controller binds both exact accepted Candidate commits/trees into TG-3's clean integration base before dispatch.
