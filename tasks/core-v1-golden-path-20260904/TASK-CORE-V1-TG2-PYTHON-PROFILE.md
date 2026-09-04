# TASK-CORE-V1-TG2-PYTHON-PROFILE — Deterministic isolated Python verifier

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `1afae6f51f91563d8476a25c220446eab8b06391b8edd99fb95ea0881828d7ed`
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
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
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
- **Required initial verification:** verify TG-0 receipt and clean exact-head isolated worker environment
- **Freshness rule:** re-read contract, source digest, image digest, lock, environment, and runner availability before each certification attempt

## MCP execution profile

- **App/server and action snapshot:** Nexus lifecycle MCP snapshot required at execution
- **Exact required actions:** nexus_task_run;nexus_task_status;nexus_task_wait;nexus_task_reconcile;nexus_task_finish
- **Confirmation-required actions:** nexus_task_run;nexus_task_finish
- **Idempotency and attempt rule:** one attempt per exact contract/source/environment; retries use new attempt and require matching fresh executions
- **Reconnect reconciliation:** reconcile durable attempt before retry; unknown effect is UNVERIFIABLE/BLOCKED
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker in isolated runner
- **Verification authority:** independent controller and adequate oracle receipt
- **Receipt authority:** Completion Core after trusted ingestion
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/execution/__init__.py;product/evidence/ingestion.py;product/verification/__init__.py;tests/product/test_kernel.py;tests/product/test_trusted_evidence_ingestion.py
- **Edit:** product/execution/__init__.py;product/evidence/ingestion.py
- **Create:** product/execution/python_runner.py
- **Delete:** none
- **Maximum touched production files:** 3
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** current execution namespace contains pure ports; no clean OCI runner is verified.
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

Use digest-pinned OCI and offline lock, shell-free argv, isolated limits, adequate JUnit oracle, two matching fresh executions; never convert unavailable or unknown to success.

## GREEN and regression gates

AC-003 and AC-004 pass only with exact contract/version/source/environment binding and the complete oracle truth table.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG2-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_kernel.py tests/product/test_trusted_evidence_ingestion.py` | runner binding regression | all tests pass |
| TG2-02 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture profile/image/lock digests, run and attempt IDs, source/environment/command/stdout/stderr/exit/artifact hashes, two-run comparison, Candidate commit, and final receipt.

## Independent review

Fresh reviewer validates isolation, oracle adequacy, determinism, exact bindings, negative controls, and no host/network escape.

## Exit conditions

- **PASS:** Candidate and isolated matrix support `PYTHON_PROFILE_VERIFIED`.
- **BLOCK:** inadequate oracle, unavailable/unclean runner, nondeterminism, or missing binding.
- **Residual debt:** trusted ingestion and runtime remain downstream.
- **Next gate:** TG-3 consumes accepted acquisition and runner identity contracts.
