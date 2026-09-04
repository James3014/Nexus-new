# TASK-CORE-V1-TG6-CLIENTS-PACKAGE — Thin clients and operator journey

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#770`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
- **Source groups:** TG-6 Thin clients/package
- **Requirements:** REQ-012;REQ-013
- **Acceptance:** AC-011;AC-012
- **Auto-chain:** `false`
- **Maximum claim:** `OPERATOR_JOURNEY_VERIFIED`
- **Depends on:** TASK-CORE-V1-TG5-HTTP-TRACER
- **Dependency unlock evidence:** TG-5 accepted receipt
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `EXPAND_CONTRACT`
- **Scope class:** `medium`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

Route CLI, MCP, and GitHub Action through canonical HTTP and provide a reproducible certification-first install, upgrade, and rollback journey.

## Observable outcome

client parity and clean install journey

## Non-goals

No client-local trust/completion logic, legacy deletion, release, deployment, production, Stable, or public value claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-012 | client behavior | all clients call HTTP and preserve canonical semantics |
| REQ-013 | packaging | install/quickstart/upgrade/rollback preserve receipts |
| AC-011 | canary witness | no semantic divergence or client-only minting |
| AC-012 | journey witness | clean install and rollback preserve readable history |

## Owner decisions

DEC-004; DEC-007; DEC-010; DEC-011. Distribution identity is `nexus-core` at existing version `28.3.0`; CLI is `nexus-certify`; legacy `nexus` remains compatibility-only.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-5 accepted live HTTP receipt and a clean controller-bound integration HEAD/tree containing the exact accepted TG-1 through TG-5 Candidate commits; this card's `Parallel safe: false` forbids auto-start but the separate Owner/controller contract permits concurrent TG-6/TG-7 dispatch as distinct Ready Issues
- **Freshness rule:** re-read TG-5 contract, package metadata, protocol/ledger versions, and client artifacts before each canary

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #770
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** each canary run binds canonical request and client artifact; exact replay returns same receipt
- **Reconnect reconciliation:** reconcile same attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane
- **Verification authority:** independent controller conformance/install/rollback checks; worker PASS is not acceptance
- **Receipt authority:** canonical HTTP/Core/ledger surfaces
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** README.md;pyproject.toml;product;tests/product;.github/actions
- **Edit:** README.md;pyproject.toml
- **Create:** product/clients/__init__.py;product/clients/cli.py;product/clients/mcp.py;product/clients/github_action.py;tests/product/test_client_conformance.py;.github/actions/nexus-certify/action.yml
- **Delete:** none
- **Maximum touched production files:** 7
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** README/package remain orchestration-first; current distribution is `nexus-singularity` version `28.3.0`; no client conformance path is verified.
- **Assumptions requiring verification:** exact `nexus-certify` entry point, MCP/Action surfaces, wheel identity, dependency lock, protocol/schema compatibility, upgrade format, prior receipt reader, and rollback command.
- **Architecture risks:** client logic may become parallel semantic owner.
- **Evidence risks:** local unit parity is not install/rollback canary evidence.
- **Missing owner decision:** none

## Canonical client/package contract

- `pyproject.toml` changes the distribution name from `nexus-singularity` to the Owner-adopted `nexus-core` while retaining version `28.3.0`; the exact wheel filename is therefore `nexus_core-28.3.0-py3-none-any.whl` for this card.
- `nexus-certify` is the new certification-first entry point and is transport-only: it calls the canonical HTTP endpoints and cannot construct a trust decision, disposition, or receipt locally.
- `product/clients/cli.py`, `product/clients/mcp.py`, and `product/clients/github_action.py` must submit the same canonical request and return canonically equivalent response/receipt data. `.github/actions/nexus-certify/action.yml` is the exact Action surface.
- `pyproject.toml` must expose `nexus-certify` while preserving the legacy `nexus` entry point as an explicitly legacy/lab compatibility surface; no hidden legacy semantics may be required by the certification journey.
- Package identity, wheel filename, Python requirement, dependency lock, protocol version, implementation schema, receipt schema, and artifact digest are recorded in the install receipt. Upgrade refuses incompatible protocol/schema/ledger combinations. Rollback restores the prior reader/runtime and leaves append-only receipt history byte-for-byte readable.

## Mandatory source audit

Audit package metadata, README quickstart, client entry points, canonical HTTP contract, protocol/ledger versions, and legacy compatibility behavior.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Negative canaries replace HTTP response, attempt receipt minting, use incompatible ledger/protocol, and omit prior reader; each must fail closed.

## Implementation constraints

Clients transport only; package remains local-first; upgrade preserves receipt history; rollback restores prior reader/runtime; no legacy deletion.

## GREEN and regression gates

AC-011 and AC-012 pass with all three client paths hitting canonical HTTP and clean install/upgrade/rollback canaries.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG6-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_client_conformance.py` | CLI/MCP/Action canonical HTTP parity and no local truth | all tests pass |
| TG6-02 | TARGET_ROOT | `uv build --wheel --out-dir /private/tmp/nexus-core-v1-wheel` | reproducible wheel artifact | one hash-bound wheel is produced |
| TG6-03 | TARGET_ROOT | `python -m venv /private/tmp/nexus-core-v1-clean-install` | create isolated clean install environment | clean environment is created |
| TG6-04 | TARGET_ROOT | `/private/tmp/nexus-core-v1-clean-install/bin/pip install --no-deps /private/tmp/nexus-core-v1-wheel/nexus_core-28.3.0-py3-none-any.whl` | install the exact distribution/version wheel emitted by TG6-02 and discover entry points | `nexus-certify` is callable and `nexus` remains legacy/lab |
| TG6-05 | TARGET_ROOT | `/private/tmp/nexus-core-v1-clean-install/bin/nexus-certify --self-test-install-upgrade-rollback` | certification-first install/upgrade/rollback canary | compatible upgrade and tested rollback preserve readable receipts; incompatible inputs fail closed |
| TG6-06 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture exact wheel/artifact and dependency-lock hashes, environment, protocol/schema/ledger versions, canonical request/response, all three client parity results, install/upgrade/rollback receipts, prior-reader readability, Candidate, and canary hashes.

## Independent review

Fresh reviewer checks thinness, parity, package reproducibility, compatibility, rollback, receipt readability, tests, and claim ceiling.

## Exit conditions

- **PASS:** canaries support `OPERATOR_JOURNEY_VERIFIED`.
- **BLOCK:** semantic divergence, client-local truth, missing exact entry point/action surface, non-reproducible artifact, missing rollback reader, incompatible history, or legacy hidden dependency.
- **Residual debt:** representative corpus and value remain.
- **Next gate:** TG-8 may consume TG-6 and TG-7 evidence after external selection.
