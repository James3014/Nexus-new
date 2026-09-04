# TASK-CORE-V1-TG5-HTTP-TRACER — Canonical local HTTP real-PR tracer

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#769`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
- **Source groups:** TG-0 Boundary/version/crosswalk freeze;TG-1 Live GitHub acquisition;TG-2 Python profile;TG-3 Evidence Trust extraction;TG-4 Durable ledger/reconciliation;TG-5 HTTP tracer bullet
- **Requirements:** REQ-003;REQ-004;REQ-007;REQ-008;REQ-009;REQ-010;REQ-011;REQ-012
- **Acceptance:** AC-002;AC-004;AC-005;AC-006;AC-007;AC-008;AC-009;AC-014
- **Auto-chain:** `false`
- **Maximum claim:** `REAL_PR_TRACER_BULLET_VERIFIED`
- **Depends on:** TASK-CORE-V1-TG1-GITHUB-ACQUISITION;TASK-CORE-V1-TG2-PYTHON-PROFILE;TASK-CORE-V1-TG3-EVIDENCE-TRUST;TASK-CORE-V1-TG4-LEDGER-RECONCILIATION
- **Dependency unlock evidence:** TG-1 receipt;TG-2 receipt;TG-3 receipt;TG-4 receipt
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

Expose the four-endpoint loopback bearer-authenticated HTTP contract and complete the controlled `James3014/Nexus-new#635` PR through acquisition, runner, trust, completion, ledger, and inspectable receipt.

## Observable outcome

real PR to inspectable receipt

## Non-goals

No remote control plane, mutation, client duplication, approval, merge, deployment, release, production, or Stable claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-003 | product journey | exactly real PR through inspectable receipt, read-only |
| REQ-004 | acquisition seam | authenticated immutable PR snapshot remains exact |
| REQ-007 | runner seam | only adequate deterministic oracle can certify |
| REQ-008 | trust seam | only authenticated, provenance-bound evidence is consumed |
| REQ-009 | completion boundary | factual tri-state and bounded disposition |
| REQ-010 | retry seam | idempotency/CAS/reconciliation survive interruption |
| REQ-011 | ledger seam | receipt history recovers without claim elevation |
| REQ-012 | transport owner | HTTP canonical; clients remain thin |
| AC-002 | acquisition seam | exact live subject survives end-to-end |
| AC-004 | runner seam | oracle truth remains bound |
| AC-005 | trust seam | hostile evidence cannot certify |
| AC-006 | claim seam | caller cannot mint higher truth |
| AC-007 | retry seam | idempotency/CAS/reconciliation survive interruption |
| AC-008 | ledger seam | receipt history recovers |
| AC-009 | tracer seam | four endpoints expose canonical semantics |
| AC-014 | journey witness | one real PR traverses all stages without mutation |

## Owner decisions

DEC-002; DEC-004; DEC-007; DEC-009.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify Issue #549 only as `ADVISORY_CACHE_ONLY`; then verify TG-1 through TG-4 accepted receipts and a clean controller-bound integration HEAD/tree containing exactly their accepted Candidate commits with recorded conflict-free composition, the accepted TG-4 API below, loopback port availability, token-file permissions, Docker/runner availability, and controlled PR #635 read access
- **Freshness rule:** re-read all upstream contracts, source revision, and local HTTP permission/auth state before each E2E run

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #769
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** canonical request hash plus idempotency key; exact replay returns same run/receipt, drift reconciles and fails closed
- **Reconnect reconciliation:** status/reconcile same request attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane
- **Verification authority:** independent controller live local E2E; worker PASS is not acceptance
- **Receipt authority:** Evidence Trust, Completion Core, and carrying ledger
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/acquisition;product/adapters/github.py;product/execution;product/evidence/ingestion.py;product/certification/receipt.py;product/ledger.py;tests/product
- **Edit:** none
- **Create:** product/runtime/__init__.py;product/runtime/schemas.py;product/runtime/auth.py;product/runtime/http.py;product/runtime/service.py;tests/product/test_http_runtime.py;tests/product/test_http_e2e.py
- **Delete:** none
- **Maximum touched production files:** 5
- **Maximum touched test files:** 2

## Unknown scan

- **Known facts:** current execution exports pure ports and no canonical HTTP runtime.
- **Assumptions requiring verification:** endpoint schemas/statuses, loopback binding, bearer token source, request limits/timeouts, lifecycle behavior, durable CAS/reconciliation, and live GitHub credentials.
- **Architecture risks:** runtime could duplicate trust/completion logic.
- **Evidence risks:** simulated HTTP or caller-supplied snapshots are insufficient.
- **Missing owner decision:** none

## Canonical HTTP contract

- **Bind:** `127.0.0.1:8767` by default; wildcard, `0.0.0.0`, IPv6-any, and non-loopback binds are rejected before listening.
- **Runtime library:** use the already locked `aiohttp` server surface; no dependency, lock, package, or workflow changes are allowed. `httpx` may be used only by tests/clients, never as a second server or semantic owner.
- **Authentication:** per-install bearer token is read only from `$XDG_CONFIG_HOME/nexus-core/token`, falling back to `~/.config/nexus-core/token`. It is ASCII base64url without padding or whitespace/newline, 43 characters, and compared in constant time. Secure open uses `O_NOFOLLOW` where available plus `lstat/fstat` identity checks; require current UID, regular file, link count one, exact mode `0600`, config directory mode `0700`, and reject symlink/replacement/permission drift before listening. Token bytes never enter responses, logs, exceptions, receipts, hashes, or worker input. Every missing/malformed/mismatched case returns the identical 401 envelope without invoking route/core/ledger logic.
- **Endpoints:** `POST /v1/certifications`, `GET /v1/certifications/{request_id}`, `GET /v1/certifications/{request_id}/receipt`, and `POST /v1/receipts/verify`.
- **Request schema:** `POST /v1/certifications` accepts only `application/json` and exact keys `protocol_version`, `implementation_schema`, `repository`, `acceptance_contract`, `verification_plan`, `profile_id`, `idempotency_key`, and `expected_generation`. `repository` has exact keys `owner`, `name`, `pr_number`, `expected_base_sha`, `expected_head_sha`; contract/plan use their canonical Product serializers with unknown fields rejected. IDs are normalized non-empty strings, SHA/hash fields retain their canonical validators, profile is exactly `python-oci-pytest-v1`, and canonical request hash is UTF-8 JSON with sorted keys and compact separators. Nulls and unknown/duplicate JSON keys are rejected.
- **Response schema:** every success is `nexus.core.http-response.v1` with exact keys `request_id`, `state`, `generation`, `acquisition`, `execution`, `evidence`, `verification`, `disposition`, `receipt`, `claim_ceiling`; unavailable sections are explicit `null`, never omitted. `state` is one of `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `UNVERIFIABLE`. Error envelope is exactly `nexus.core.http-error.v1` with `code`, `request_id`, and generic `message`; it contains no internal exception or credential detail.
- **Receipt verify schema:** `POST /v1/receipts/verify` accepts exact `nexus.core.receipt-verify-request.v1` keys `receipt`, `requested_scope`, `original_inputs`; `requested_scope` is `AUTO`, `ENVELOPE_ONLY`, or `FULL`, and `original_inputs` is null unless exact stored contract/change/plan/evidence payloads are supplied. Response `nexus.core.receipt-verify-response.v1` has exact keys `scope`, `status`, `reason_codes`, `receipt_hash`, `recomputed_hash`, `claim_ceiling`; scope is `ENVELOPE_ONLY` or `FULL_RECOMPUTED`, status is `VALID`, `INVALID`, or `UNVERIFIABLE`. `FULL` without complete original inputs returns `UNVERIFIABLE`, never envelope-only success.
- `product/runtime/schemas.py` is the canonical named artifact and exports `CERTIFICATION_REQUEST_SCHEMA`, `HTTP_RESPONSE_SCHEMA`, `HTTP_ERROR_SCHEMA`, `RECEIPT_VERIFY_REQUEST_SCHEMA`, `RECEIPT_VERIFY_RESPONSE_SCHEMA`, and `SCHEMA_BUNDLE_HASH`, computed over canonical JSON of all five schemas. TG-6 clients bind semantic and canonical-serialization equivalence to this bundle hash.
- **Limits/timeouts:** request body `1,048,576` bytes, request-target/path `512` bytes, request/idempotency IDs `128` bytes, result body `8,388,608` bytes, header/read-parse timeout `10s`, graceful in-flight shutdown `30s`, and verifier worker timeout `330s` (covering the TG-2 300s profile). Boundary+1 inputs fail before durable state. Timeout/unknown effect becomes `UNVERIFIABLE` plus reconciliation before retry.
- **Durability:** exact `(idempotency_key, canonical_request_hash)` replay returns the original run/receipt; same key with changed request, stale generation/source, or changed subject fails closed through SQLite generation CAS and reconciliation.
- **Receipt verification:** `/verify` returns `ENVELOPE_ONLY` unless stored original inputs allow full recomputation; it cannot elevate the claim ceiling.

### Status and error matrix

| Operation | Condition | HTTP | Machine code/state | Durable effect |
|---|---|---:|---|---|
| POST certification | new valid request accepted | 202 | `PENDING` or `RUNNING` | one reserved/reconcilable request identity |
| POST certification | exact replay | 200 if terminal, otherwise 202 | original state/request ID | none |
| POST certification | same key, changed request | 409 | `IDEMPOTENCY_CONFLICT` | none |
| POST certification | stale generation/source/subject | 409 | `STALE_GENERATION` / `STALE_SOURCE` | none |
| POST certification | malformed/unknown/null/oversized/unsupported version/profile | 400/413/415/422 as applicable | `MALFORMED_REQUEST`, `REQUEST_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `UNSUPPORTED_CONTRACT` | none |
| GET status | known request | 200 | exact current state | none |
| GET status/receipt | unknown normalized ID | 404 | `REQUEST_NOT_FOUND` | none |
| GET receipt | known nonterminal request | 409 | `RESULT_NOT_READY` | none |
| GET receipt | terminal request | 200 | stored exact receipt | none |
| POST receipt verify | valid stored full inputs | 200 | `FULL_RECOMPUTED` | none |
| POST receipt verify | structurally valid envelope only | 200 | `ENVELOPE_ONLY` | none |
| POST receipt verify | malformed/tampered/unknown receipt | 422 | `RECEIPT_INVALID` | none |
| any endpoint | missing/malformed/wrong bearer token | 401 | `UNAUTHORIZED` | no route/core/ledger call |
| unsupported method on known route | authenticated | 405 | `METHOD_NOT_ALLOWED` | none |
| unknown/malformed path | authenticated | 404 | `ROUTE_NOT_FOUND` | none |
| worker timeout/ambiguous effect | accepted request | 202/409 on reconciliation query | `UNKNOWN_EFFECT_RECONCILIATION_REQUIRED` then exact durable result or `UNVERIFIABLE` | never duplicate |

Authentication runs before route-specific disclosure, so unauthenticated unknown paths/methods receive the identical 401 envelope. Malformed request IDs never reach core or ledger.

### Runtime lifecycle and TG-4 ownership

- `product/runtime/http.py` exposes `create_app` without listening; `start_runtime` performs token and TG-4 ledger preflight before binding, binds only the configured loopback address, reports readiness only after socket acquisition, and fails atomically on auth/ledger/bind error. `stop_runtime` stops admission, waits at most 30 seconds for in-flight work, durably reconciles committed effects, marks unresolved work `UNVERIFIABLE`, releases the socket, and supports repeated start/stop without stale process/port state.
- One aiohttp event loop owns server tasks; background verifier work is bounded and every task is joined/cancelled at shutdown. Starting twice or binding an occupied/non-loopback port fails without a second listener. Tests exercise startup failure, graceful/forced shutdown, in-flight retry, repeated lifecycle, port reuse, and no orphan task/thread.
- TG-5 calls only accepted TG-4 `append_or_replay`, `get_by_request_id`, `verify_chain`, and `verify_external_anchor`. It may keep ephemeral in-flight futures but SHALL NOT create a second durable idempotency, generation, reconciliation, receipt, or CAS owner.
- Upstream mapping is exact: TG-1 owns `repository_owner/name`, PR number, base/head commits and trees, diff hash, changed/deleted paths, checks and freshness CAS; Acceptance Contract/Plan own their hashes; TG-2 owns source revision/tree, environment/profile and physical attempts; TG-3 envelope owns producer/issuer, acquisition/runner/verification receipt hashes and generation; TG-4 owns request/idempotency/current committed generation, stored payload and ledger entry/head hashes. Duplicated copies must be byte-equal or the request fails `CROSS_BOUND_UPSTREAM_IDENTITY` before append.

### Worker/controller test split

- Luna runs deterministic fake-port HTTP tests only: `uv run pytest -qq tests/product/test_http_runtime.py tests/product/test_http_e2e.py -m "not live"`. Tests register `live` and `--run-live` in the local module/plugin surface without editing global pytest configuration; absent `--run-live` is an explicit skip, never a pass claim.
- The controller alone supplies GitHub credentials and runs the authenticated #635 probe after Candidate commit. The controller command is `NEXUS_CORE_HTTP_PORT=8767 uv run pytest -qq tests/product/test_http_e2e.py -m live --run-live`; its fixture calls the credential-free TG-1 port, redacts all auth material, verifies the test actually executed (not skipped), and persists only the exact PR/acquisition/runtime/receipt hashes.

## Exact upstream identity tuple

TG5 may run only after accepted TG1–TG4 receipts bind this exact tuple: `(repository_owner, repository_name, pr_number, base_sha, head_sha, tree_sha, diff_hash, changed_paths, contract_hash, plan_hash, environment_hash, source_revision, source_tree, attempt_id, generation)`. Missing, duplicate, or cross-bound tuple members are a hard fail.

## Controlled real-PR fixture

Use the pre-existing read-only fixture `James3014/Nexus-new#635`; immediately before the run, record and independently re-read its full base/head/tree/diff/check identities. The Candidate PR under implementation must not be used as its own fixture unless the controller records a separate Owner-approved fixture decision.

## Mandatory source audit

Audit upstream contracts and receipts, protocol/schema axes, auth/loopback policy, ledger identity, all client boundaries, and real-PR E2E test seams.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Negative E2E cases cover idempotency/request/version drift, interrupted request, direct caller result, stale source, inadequate oracle, and unknown effect.

## Implementation constraints

Bind only to 127.0.0.1 with per-install bearer token; retain four endpoints; delegate truth to the two cores; persist/reconcile durable state; never mutate PR.

## GREEN and regression gates

AC-002 and AC-004 through AC-009 pass only on a live local E2E from authenticated real PR to receipt and all negative controls.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG5-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_http_runtime.py tests/product/test_http_e2e.py -m "not live"` | Luna-owned runtime, auth, schema, replay, lifecycle, and injected-port tracer regression | all deterministic tests pass; live tests deselected |
| TG5-02 | TARGET_ROOT | `NEXUS_CORE_HTTP_PORT=8767 uv run pytest -qq tests/product/test_http_e2e.py -m live --run-live` | controller-only authenticated `James3014/Nexus-new#635` acquisition-to-receipt E2E and negative controls | live tests execute with zero skips and all hostile cases pass |
| TG5-03 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture loopback/auth configuration (including token path/mode without token contents), canonical request, exact TG1–TG4 tuple and receipt hashes, idempotency/run/acquisition/evidence/result/response/receipt hashes, live #635 E2E, interruption/replay outcomes, Candidate commit, and final state.

## Independent review

Fresh reviewer validates endpoint contract, auth/loopback, core delegation, exact real-PR subject, durable reconciliation, negative controls, tests, and claim ceiling.

## Exit conditions

- **PASS:** live local E2E for the bound #635 fixture supports `REAL_PR_TRACER_BULLET_VERIFIED`.
- **BLOCK:** missing live acquisition, missing TG1–TG4 tuple member, bypassed core, duplicate truth, auth/loopback drift, schema/limit ambiguity, or unknown effect.
- **Residual debt:** clients/package and cross-repo value remain.
- **Next gate:** after controller acceptance, TG-6 and TG-7 are parallel-ready; neither auto-activates.
