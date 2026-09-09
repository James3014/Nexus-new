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

- **Read:** README.md;pyproject.toml;uv.lock;product;tests/product;.github/actions;scripts/engine/nexus_cli.py
- **Edit:** README.md;pyproject.toml;uv.lock;scripts/engine/nexus_cli.py
- **Create:** product/clients/__init__.py;product/clients/cli.py;product/clients/mcp.py;product/clients/github_action.py;tests/product/test_client_conformance.py;.github/actions/nexus-certify/action.yml
- **Delete:** none
- **Maximum touched production files:** 9
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** README/package remain orchestration-first; current distribution is `nexus-singularity` version `28.3.0`; no client conformance path is verified.
- **Assumptions requiring verification:** exact `nexus-certify` entry point, MCP/Action surfaces, wheel identity, dependency lock, protocol/schema compatibility, upgrade format, prior receipt reader, and rollback command.
- **Architecture risks:** client logic may become parallel semantic owner.
- **Evidence risks:** local unit parity is not install/rollback canary evidence.
- **Missing owner decision:** none

## Canonical client/package contract

- `pyproject.toml` changes both `[project].name` and `[tool.poetry].name` from `nexus-singularity` to Owner-adopted `nexus-core`, retains version `28.3.0`, and synchronizes `[project.scripts]` with `[tool.poetry.scripts]`. Poetry remains the build backend; both metadata surfaces must emit `nexus_core-28.3.0-py3-none-any.whl`. `uv.lock` is updated mechanically and must name the root package `nexus-core` at the same source/tree.
- Default `nexus-core` installation contains `product` plus a dependency-light legacy shim and requires only the already-locked Core runtime set (`aiohttp>=3.13.5,<4`). The former orchestration/ML dependency set moves without version widening into optional extra `legacy`; existing `ml`, `web3`, and `browser` extras remain separate. Clean Core install must not resolve or import legacy/ML dependencies; wheel metadata proves this.
- `nexus-certify` is the new certification-first entry point and is transport-only: it calls the canonical HTTP endpoints and cannot construct a trust decision, disposition, or receipt locally.
- `product/clients/cli.py`, `product/clients/mcp.py`, and `product/clients/github_action.py` must submit the same canonical request and return canonically equivalent response/receipt data. `.github/actions/nexus-certify/action.yml` is the exact Action surface.
- Both script tables expose `nexus-certify = product.clients.cli:main` and preserve `nexus = scripts.engine.nexus_cli:nexus`. `scripts/engine/nexus_cli.py` may be edited only to make imports lazy and return stable `LEGACY_EXTRA_REQUIRED`/exit 78 when a non-help legacy command lacks the optional extra; `nexus --help` remains callable and labels the surface legacy/lab. Certification code must not import or invoke legacy orchestration modules.
- Package identity, wheel filename, Python requirement, dependency lock, protocol version, implementation schema, receipt schema, and artifact digest are recorded in the install receipt. Upgrade refuses incompatible protocol/schema/ledger combinations. Rollback restores the prior reader/runtime and leaves append-only receipt history byte-for-byte readable.

### Exact client contracts

- CLI commands are `nexus-certify submit --request FILE --url http://127.0.0.1:8767`, `status REQUEST_ID`, `receipt REQUEST_ID`, and `verify --receipt FILE`. Input/output use exact TG-5 schemas; canonical JSON goes to stdout and diagnostics only to stderr. Exit codes are `0` success, `2` usage/schema, `3` authentication, `4` not found, `5` conflict/stale, `6` factual `UNVERIFIABLE`, `7` transport/timeout. Header/read timeout is 10s and certification wait timeout 330s. Token contents never appear in argv or output; clients read only the protected token path.
- `product.clients.mcp` is a host-projected library adapter, not a new MCP server/stdio daemon. It exposes one callable tool contract `nexus_certify(arguments, http_transport)` whose JSON Schema is byte-equivalent to TG-5 request/response schemas and whose only effect is canonical HTTP. It adds no MCP dependency and owns no trust/completion logic.
- `.github/actions/nexus-certify/action.yml` supports only a self-hosted runner with TG-5 ready on loopback. Exact inputs are `request-file`, optional `service-url` default `http://127.0.0.1:8767`, and `token-file`; outputs are `request-id`, `state`, `receipt-file`, `claim-ceiling`. Because `permissions` is workflow-level, action metadata documents and validates the caller prerequisite `permissions: contents: read, pull-requests: read` rather than declaring an invalid key. Runtime requires `RUNNER_ENVIRONMENT=self-hosted` and loopback URL, otherwise exits `HOSTED_RUNNER_FORBIDDEN`/78 before reading the token. It invokes the Python thin client, passes only token-file path, masks output, and never starts/exposes/tunnels service.
- MCP/CLI/Action schemas bind to `product/runtime/schemas.py` exports and exact `SCHEMA_BUNDLE_HASH`; parity means identical canonical serialization and semantics, not textual equality to prose.
- One test constant inside `test_client_conformance.py` contains the canonical request/response pair. CLI, MCP adapter and Action wrapper produce byte-equivalent redacted payloads and the same endpoint sequence; altered responses, client-minted disposition/receipt, or extra semantic fields fail.

### Build, install, upgrade, and rollback contract

- Build twice in fresh output directories with `SOURCE_DATE_EPOCH` bound to Candidate commit time. Wheel filename, bytes/hash, file list, METADATA, entry points and RECORD must match. Package data includes runtime protocol/profile schemas and excludes tests, credentials, state/evidence, `.git`, caches and optional legacy dependencies.
- Controller materializes `/private/tmp/nexus-core-v1-wheelhouse` before install and writes `wheelhouse-manifest.json` schema `nexus.core-v1.tg6-wheelhouse.v1` with exact Python/platform, source lock hash, separate build-A/build-B hashes/file lists, selected-successor hash, sorted distribution/version/filename/SHA-256 closure rows, closure hash, generated-at and manifest hash. Build A/B stay in separate directories because their filenames are identical; wheelhouse stages exactly one byte-selected successor plus locked `aiohttp` closure and rejects duplicate logical distributions, extra/missing/wrong-hash files. Clean installation uses new venv and `pip install --no-index --find-links`; `--no-deps` is forbidden. Verify manifest, every wheel hash, `pip check`, METADATA, CLI help and one TG-5 journey.
- Predecessor is `nexus_singularity-28.3.0-py3-none-any.whl` built from exact accepted TG-5 integration base before package edits; successor is `nexus_core-28.3.0-py3-none-any.whl`. Migration stops service, uninstalls predecessor, installs successor, preserves XDG token/ledger/state, and proves successor reads a hash-bound pre-upgrade receipt.
- Rollback stops service, uninstalls `nexus-core`, reinstalls exact predecessor plus locked legacy environment, and proves pre-upgrade receipt remains byte-identical/readable without coercing new incompatible ledger/protocol state. Compatible/incompatible matrix covers public protocol, implementation schema, receipt schema and ledger generation; failed upgrade runs the same rollback and leaves no mixed distribution metadata.

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
| TG6-02 | TARGET_ROOT | `uv run pytest -qq tests/product/test_client_conformance.py -k predecessor_artifact` | verify controller-prebuilt exact accepted TG5 predecessor wheel/source receipt | predecessor filename/hash/source/tree and METADATA match accepted TG5 base |
| TG6-03 | TARGET_ROOT | `uv build --wheel --out-dir /private/tmp/nexus-core-v1-wheel-a` | first successor build | exact `nexus_core-28.3.0-py3-none-any.whl` plus hash/file-list receipt |
| TG6-04 | TARGET_ROOT | `uv build --wheel --out-dir /private/tmp/nexus-core-v1-wheel-b` | independent successor build | wheel bytes/hash/METADATA/RECORD equal TG6-03 |
| TG6-05 | TARGET_ROOT | `uv run pytest -qq tests/product/test_client_conformance.py -k wheelhouse_manifest` | verify controller-staged wheelhouse manifest/closure | exact locked closure, no extra/missing/wrong hashes |
| TG6-06 | TARGET_ROOT | `python -m venv /private/tmp/nexus-core-v1-clean-install` | create isolated install environment | clean environment created |
| TG6-07 | TARGET_ROOT | `/private/tmp/nexus-core-v1-clean-install/bin/pip install --no-index --find-links /private/tmp/nexus-core-v1-wheelhouse nexus-core==28.3.0` | install Core wheel and closure | install succeeds and `pip check` is clean |
| TG6-08 | TARGET_ROOT | `/private/tmp/nexus-core-v1-clean-install/bin/nexus-certify --help` | certification entry point | exact CLI contract without legacy imports |
| TG6-09 | TARGET_ROOT | `/private/tmp/nexus-core-v1-clean-install/bin/nexus --help` | legacy shim | callable and explicitly legacy/lab |
| TG6-10 | TARGET_ROOT | `uv run pytest -qq tests/product/test_client_conformance.py -k install_upgrade_rollback` | predecessor/successor migration and rollback matrix | prior receipts byte-identical/readable; mixed installs fail closed |
| TG6-11 | TARGET_ROOT | `/private/tmp/nexus-core-v1-clean-install/bin/nexus-certify submit --request /private/tmp/nexus-core-v1-evidence/tg6/live-request.json --url http://127.0.0.1:8767` | controller-only clean-installed client against accepted TG5 service | real request ID/receipt equals accepted TG5 canonical response with no skips |
| TG6-12 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture exact wheel/artifact and dependency-lock hashes, environment, protocol/schema/ledger versions, canonical request/response, all three client parity results, install/upgrade/rollback receipts, prior-reader readability, Candidate, and canary hashes.

## Independent review

Fresh reviewer checks thinness, parity, package reproducibility, compatibility, rollback, receipt readability, tests, and claim ceiling.

## Exit conditions

- **PASS:** canaries support `OPERATOR_JOURNEY_VERIFIED`.
- **BLOCK:** semantic divergence, client-local truth, missing exact entry point/action surface, non-reproducible artifact, missing rollback reader, incompatible history, or legacy hidden dependency.
- **Residual debt:** representative corpus and value remain.
- **Next gate:** TG-8 may consume TG-6 and TG-7 evidence after external selection.
