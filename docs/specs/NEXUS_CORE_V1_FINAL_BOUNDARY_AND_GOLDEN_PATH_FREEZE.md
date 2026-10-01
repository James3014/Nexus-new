# Nexus Core V1 Final Boundary and Golden Path Freeze

- **Spec ID:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Status:** `READY_FOR_TASK_CARDS`
- **Basis snapshot:** `James3014/Nexus-new@785751e109e90aa66a87a863dbc223618eceeffd`, tree `79a8dd7b4bb40313e3872491fb5cd0a70bba5ba8`, clean detached snapshot `cd9fcc75416bb599e0783c1b0dbe9f20f1241b6e7c1b79629842859803a242fd`
- **Supersedes:** approved successor contract; physical old-card reconciliation remains TG-0 work and no historical artifact is rewritten
- **Claim ceiling:** `CORE_V1_SPEC_READY_FOR_TASK_CARDS`

## 1. Problem statement

Nexus contains a strong experimental certification library and Evidence Trust donor code, but it does not yet expose one installable, real-GitHub-PR, read-only Completion Certification product. Internal Gateway, lifecycle, Candidate adoption, Planner, Workforce, Learning, or executor closure is not product Golden Path proof.

## 2. Desired outcome

A local operator submits one real GitHub PR and a versioned Acceptance Contract to a canonical local HTTP service. Nexus acquires an exact immutable snapshot, runs adequate deterministic Python witnesses in a clean environment, ingests trusted evidence, derives factual verification, emits a bounded disposition and inspectable receipt, and returns `UNVERIFIABLE` whenever the oracle is inadequate.

## 3. Basis, coverage, and freshness

- Owner planning basis: attachment `/Users/jameschen/.codex/attachments/dd424ced-d574-4036-a377-aa5cdac1055f/pasted-text-1.txt`, previously hashed `8fc52d0d95afb26ee52e45c1dd62517f878a50cc63622e285b3bd5769d06be32`.
- Current source: clean, detached, non-sparse/non-shallow worktree at the exact subject above.
- Coordinator verification: `uv run pytest -qq tests/product` -> `736 passed in 6.10s`.
- Rebind from reviewed `53980fed` through `8bf586e3` to current `785751e1` changed only the canonical task seam plus G20 recovery receipt/evidence files; all Product/source seams cited here are byte-unchanged, and the Product suite was rerun on the new exact head.
- Review ledger: `/private/tmp/CORE-V1-REVIEW-LEDGER.md`; C5 Spark and B7 Luna are clean review results, A4 Opus is partial evidence, B4/MiMo produced no result, and C4 is excluded for scope violation.
- No live GitHub acquisition, product HTTP runtime, ledger restart, package install, second-repo shadow, production runtime, or commercial pilot was verified.

## 4. Source and decision ledger

| ID | Class | Statement | Authority/location | Freshness/snapshot | Status | Limitation |
|---|---|---|---|---|---|---|
| DEC-001 | DEC | Core owns exactly Evidence Trust Core and Completion Core. | Owner planning basis | attachment hash | BINDING | carrying layers are not extra cores |
| DEC-002 | DEC | First Golden Path is real GitHub PR certification and is read-only. | Owner planning basis Gate 2 | attachment hash | BINDING | no remediation/approve/merge/deploy |
| DEC-003 | DEC | Highest V1 certification is limited to deterministic/reproducible Python witnesses; inadequate oracle means `UNVERIFIABLE`. | Owner planning basis Gate 2 | attachment hash | BINDING | exact profile bound by DEC-008 |
| DEC-004 | DEC | Local HTTP is canonical; CLI, MCP, and GitHub Action are thin clients. | Owner planning basis Gates 1 and 3 | attachment hash | BINDING | exact surface bound by DEC-007 |
| DEC-005 | DEC | Public Stable requires real vertical, representative corpus, second-repo shadow, compatibility, upgrade, and rollback. | Owner planning basis Gate 5 | attachment hash | BINDING | launch/value later |
| DEC-006 | DEC | Controller plans and accepts; workers return bounded evidence and do not self-approve. | current Owner goal | current thread | BINDING | no mutation/merge authority |
| DEC-007 | DEC | Adopt the four-endpoint loopback-only bearer-authenticated JSON HTTP contract, durable idempotency/reconciliation, separate protocol/schema axes, and envelope-only versus full receipt verification scope. | Owner adoption `ADOPT_CORE_V1_DECISION_BUNDLE_D_HTTP_D_RUNNER_D_LEDGER_D_SUPERSESSION` | 2026-09-04 decision packet SHA `1297b99a...` | BINDING | no remote control plane or approval authority |
| DEC-008 | DEC | Adopt `python-oci-pytest-v1` as the sole highest-certification Python profile: digest-pinned OCI, offline locked dependencies, shell-free argv, isolation/limits, adequate JUnit oracle, two matching fresh executions, durable attempt evidence. | same Owner adoption | 2026-09-04 | BINDING | host runner may produce lower diagnostic evidence only |
| DEC-009 | DEC | Adopt append-only SQLite WAL/full-sync ledger with transactional idempotency/generation CAS, hash-linked entries, corruption fail-closed inspection, and optional external Ed25519 signing with external private-key custody and no claim elevation. | same Owner adoption | 2026-09-04 | BINDING | exact implementation remains Task Card work |
| DEC-010 | DEC | Preserve the old Local ChangeSet card/history unchanged; after adoption, reconcile/supersede additively through formal governance, using a supported terminal compatibility state when available and never inheriting its authority. | same Owner adoption | 2026-09-04 | BINDING | TG-0 must verify formal supported state |
| DEC-011 | DEC | Adopt operational defaults: HTTP `127.0.0.1:8767`; mode-0600 bearer token at `$XDG_CONFIG_HOME/nexus-core/token` or `~/.config/nexus-core/token`; GitHub credentials injected through a secret-free provider boundary; SQLite at `$XDG_STATE_HOME/nexus-core/ledger.sqlite3` or `~/.local/state/nexus-core/ledger.sqlite3`; distribution `nexus-core`; CLI `nexus-certify`; controlled live fixture PR #635. | Owner statement “其他我看過了，都同意” | 2026-09-04 | BINDING | secrets never enter receipts/logs/workers |
| DEC-012 | DEC | SQLite/hash-chain evidence covers atomicity and detectable corruption, torn-tail, and reorder; arbitrary rollback to an older valid ledger is `ANCHOR_UNAVAILABLE`/`UNVERIFIABLE` unless verified against an external signed head anchor. | same Owner statement + controller reconciliation | 2026-09-04 | BINDING | no false arbitrary-rollback claim |
| DEC-013 | DEC | Separate cross-repo trust, public protocol maturity, and commercial value into distinct gates; value requires at least 30% paired human-verification-time improvement including Nexus overhead, no trust regression, 3–5 design partners, 4–8 weeks, and continuation or paid signal. | Owner planning basis Gate 6 + same Owner statement | 2026-09-04 | BINDING | no automatic release or production claim |
| CON-001 | CON | Root `AGENTS.md` separates implementation, verification, acceptance, merge, release, and production authority. | `AGENTS.md` | current snapshot | BINDING | this spec creates no execution authority |
| CUR-001 | CUR | Public protocol is `0.1.0-experimental`; implementation schema is `nexus.changeset_certification.v2`. | `product/protocol/__init__.py:1-7` | current snapshot | EVIDENCE | separate version axes |
| CUR-002 | CUR | GitHub adapter accepts a pre-materialized structural snapshot and owns no network or mutation surface. | `product/adapters/github.py:1-7,31-69,103-116,228-258`; `tests/product/test_github_adapter.py:276-311` | current snapshot | EVIDENCE | not live/authenticated acquisition |
| CUR-003 | CUR | Product execution contains only pure request/response ports. | `product/execution/__init__.py:1-17` | current snapshot | EVIDENCE | no HTTP implementation |
| CUR-004 | CUR | Kernel derives verification, disposition, and receipt from exact contract/change/plan/evidence and explicit prerequisite fields. | `product/kernel/__init__.py:23-33,74-123` | current snapshot | EVIDENCE | in-process library only |
| CUR-005 | CUR | Evidence ingestion binds producer, issuer, provenance, execution/attempt, repository/revision/tree, freshness, and external verification receipt identities. | `product/evidence/ingestion.py:141-524,699-735,903-918`; `product/adapters/trusted.py:34-105,314-437` | current snapshot | EVIDENCE | signature verification and live acquisition external |
| CUR-006 | CUR | Completion reducer preserves `VERIFIED`, `FAILED_VERIFICATION`, and `UNVERIFIABLE`; receipt has a fixed claim ceiling. | `product/verification/__init__.py:14-51,82-129`; `product/certification/__init__.py:8-80`; `product/certification/receipt.py:29-35,103-187` | current snapshot | EVIDENCE | no product runtime/retry state |
| CUR-007 | CUR | Fixed Product suite passes 736 tests; fixed corpus contains 25 cases with 24 hostile cases. | coordinator test; `tests/product/test_false_completion_benchmark.py:35-52` | current snapshot | EVIDENCE | fixed local corpus is not representative proof |
| CUR-008 | CUR | README/package/CLI remain v28.3 orchestration/swarm-first. | `README.md:1-39`; `pyproject.toml:1-30,52-75` | current snapshot | EVIDENCE | product cutover absent |
| CUR-009 | CUR | Existing Local ChangeSet card is ACTIVE/candidate-pending and explicitly excludes GitHub/runtime operations. | `tasks/productization-local-changeset-certification-v1-20260817/00-contract-freeze.md:1-49` | current snapshot | EVIDENCE | cannot authorize new Golden Path |
| DER-001 | DER | `product/adapters/trusted.py` is a donor/Core Candidate for Evidence Trust prerequisite semantics, not a final third owner. | DEC-001 + CUR-005 + review ledger | current synthesis | EVIDENCE | physical destination unresolved |
| DER-002 | DER | Invariants 8-10 require product-runtime enforcement beyond current library/ingestion evidence. | DEC-002 + A4/C5 findings | current synthesis | EVIDENCE | implementation not authorized |
| DER-003 | DER | Selection of the second repository and design-partner cohort is work owned by TG-7 and TG-9 after their real dependencies unlock; it is not an unresolved current-owner decision. | DEC-005,DEC-013 | 2026-09-04 | EVIDENCE | no cross-repo/Stable/value claim until selected and verified |
| REJ-001 | REJ | Public protocol v1 and internal implementation schema v2 must not be treated as one version axis. | CUR-001 + controller adjudication | current synthesis | REJECTED | avoids false conflict |

## 5. Current verified state

The current Product namespace has deterministic evidence, verification, certification, receipt, trusted-ingestion, pre-materialized GitHub mapping, and hostile-test foundations. It lacks live authenticated GitHub acquisition, a clean Python runner, durable retry/reconciliation state, canonical HTTP runtime, local trust ledger, thin external clients, certification-first packaging, and cross-repository value proof.

### 5A. Ten-invariant owner and coverage crosswalk

| # | Invariant | Canonical owner | Current source seam | Consumer | Current witness | Coverage | Exact gap |
|---:|---|---|---|---|---|---|---|
| 1 | Bounded authority/scope | Evidence Trust Core | `AcceptanceContract.allowed_paths`; `product/verification/__init__.py:149-193` | Completion Core | `tests/product/test_kernel.py:77-98,238-276` | VERIFIED_BASELINE | Spec/runtime must prevent adapters from widening allowed scope. |
| 2 | Task/Attempt/repository revision identity | Evidence Trust Core | `EvidenceRequirement`, `ProvenanceEnvelope`, `TrustedIngestionContext` in `product/evidence/ingestion.py:225-520` | Product Runtime and Completion Core | `tests/product/test_trusted_evidence_ingestion.py` cross-bound execution/repository cases | VERIFIED_BASELINE | Identity is enforced at ingestion, not in the base kernel; layering must remain explicit. |
| 3 | Immutable physical Candidate/ChangeSet identity | Evidence Trust Core | `ChangeSet` and sealed hash in `product/evidence/__init__.py:211-236,466-474` | Verification | `tests/product/test_kernel.py:238-276` | VERIFIED_BASELINE | Live acquisition must prove the supplied ChangeSet corresponds to physical PR bytes/trees. |
| 4 | Revision-bound evidence | Evidence Trust Core | `derive_evidence_integrity` and bundle bindings in `product/evidence/__init__.py:264-363,703-715` | Verification | stale/cross-bound/tamper tests in `tests/product/test_kernel.py:327-359` | VERIFIED_BASELINE | Live runner/acquisition receipts do not yet exist. |
| 5 | Independent verification | Completion Core, using Evidence Trust provenance | reducer-only `VerificationResult` in `product/verification/__init__.py:82-132` | Certification reducer | kernel/result-forgery tests in `tests/product/test_kernel.py` and `test_evidence_receipt_hardening.py` | PARTIAL | Reducer authenticity is tested; physical verifier independence and adequate oracle must be proven by runner provenance. |
| 6 | Authenticated independent-acceptance provenance | Evidence Trust Core | `TrustReference` and external receipt expectation in `product/evidence/ingestion.py:393-441`; `product/adapters/trusted.py:34-105,263-437` | Completion prerequisites | `tests/product/test_trusted_certification_adapter.py` | PARTIAL | Current core validates hashes/structure; external cryptographic verification and issuer authentication remain outside and must be receipt-bound. |
| 7 | Claim ceiling/release boundary | Completion Core | `CLAIM_CEILING` and sealed `Receipt` in `product/certification/receipt.py:29-35,103-187` | Runtime/clients/humans | `tests/product/test_kernel.py:376+`; `test_evidence_receipt_hardening.py` | VERIFIED_BASELINE | Adapter-local claim ceilings must never substitute for the core receipt ceiling. |
| 8 | Ambiguous-effect reconciliation before retry | Product Runtime | no durable owner; core can emit `BLOCKED` via `product/certification/__init__.py:22-80` | HTTP clients | prerequisite-block tests only | MISSING_PRODUCT_SEAM | `BLOCKED` is not durable reconciliation. Runtime must persist request/effect state and reconcile before retry. |
| 9 | Stale/replay generation fencing and CAS | Product Runtime, validated by Evidence Trust | ingestion freshness/generation plus optional claimed hashes in `product/evidence/ingestion.py:281-310,699-735`; receipt/bundle hashes | HTTP/ledger | ingestion freshness and receipt tamper tests | PARTIAL | No durable idempotency/generation/CAS state. Optional claimed hashes mean no self-claim, not successful CAS. |
| 10 | Integration-subject freshness/requalification | Evidence Trust Core | `FreshnessStatus` and `derive_runtime_freshness` in `product/evidence/ingestion.py:54-60,699-735` | External approval/integration action | ingestion stale-subject/observation tests | PARTIAL | No product-level receipt requalification endpoint or integration consumer; Core must not gain merge authority. |

## 6. Owner decisions

`DEC-001` through `DEC-013` are binding. The former HTTP, runner, ledger, supersession, operational-default, rollback-claim, protocol-maturity, and value-gate unknowns are resolved. Second-repository and design-partner selection are execution work owned by TG-7 and TG-9; they are not unresolved Owner decisions and do not block earlier dependency groups.

## 7. Canonical terminology

- **Public protocol version:** customer-visible compatibility contract, currently `0.1.0-experimental`, later eligible for public v1 RC/Stable.
- **Implementation schema:** internal/wire implementation identity, currently `nexus.changeset_certification.v2`; it does not imply public Protocol v2.
- **Evidence Trust Core:** sole owner of evidence identity, provenance, freshness, trust, tamper/replay, producer/issuer, and prerequisite validation.
- **Completion Core:** sole owner of factual verification reduction, disposition, receipt, and claim ceiling.
- **Product Runtime:** local HTTP carrying/orchestration layer; not a truth owner.
- **Certification Receipt:** immutable bounded evidence statement; never approval, merge, deployment, release, outcome, or production truth.

## 8. Change delta

Mode: BROWNFIELD

Baseline: experimental Product kernel and Local ChangeSet contract at `785751e109e90aa66a87a863dbc223618eceeffd`.

### ADDED

Live GitHub acquisition, clean deterministic Python runner, durable reconciliation/idempotency, local ledger, canonical HTTP runtime, thin clients, installation journey, representative corpus, second-repo shadow, and value instrumentation.

### MODIFIED

- Pre-materialized GitHub adapter changes from caller-facing compatibility input to a downstream internal handoff from authenticated acquisition. From structural input alone; to provenance-bound snapshot. Reason: prevent caller-minted PR truth. Impact: `NON_BREAKING` to pure adapter but `OPERATIONAL` to product journey.
- Product identity changes from orchestration-first to Completion Certification first while legacy workflows remain explicitly lab/legacy. Impact: `BREAKING` for packaging/quickstart; requires upgrade/rollback.
- Experimental public protocol advances only through evidence gates; internal v2 implementation schema remains separately versioned. Impact: `EVIDENCE_ONLY` until RC.

### REMOVED

None. Retirement requires separate owner-authorized compatibility Task Cards.

### RENAMED

None adopted. Public naming remains within `UNK-001`.

## 9. Scope

Core ownership, ten-invariant crosswalk, real-PR acquisition, Acceptance Contract, Python verifier, evidence trust, completion semantics, receipt/ledger, HTTP runtime, thin clients, packaging, corpus, cross-repo shadow, protocol maturity, and usability/value gates.

## 10. Non-goals

Code remediation, patch application, model execution, Planner/Workforce routing, lifecycle orchestration, Learning, Open SWE, cloud/multi-tenant control, approval, merge, deploy, release, production readiness, outcome truth, automatic commercial claims, or automatic successor activation.

## 11. User and operator stories

1. A local operator submits a real PR and Acceptance Contract without granting mutation authority.
2. A reviewer inspects and independently revalidates an exact receipt.
3. CLI, MCP, and GitHub Action users receive semantics identical to direct HTTP.

## 12. Architecture and authority boundaries

```text
GitHub read-only acquisition      Clean Python verifier
            \                         /
             -> Evidence Trust Core -> Completion Core
                         |                    |
                   trusted evidence     bounded receipt
                              \          /
                           Local Trust Ledger
                                  |
                     Canonical Local HTTP Runtime
                       /          |           \
                     CLI         MCP     GitHub Action
```

Evidence Trust and Completion are the only truth owners. Runtime and clients transport inputs/results. Policy, authority, approval, and signing may be verified as external prerequisites but the Core cannot create those authorities.

## 13. Requirements

### REQ-001 — Two-core ownership
- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-006, CON-001, DER-001`
- **Behavior:** The product SHALL have exactly Evidence Trust Core and Completion Core as permanent truth owners and SHALL NOT add a parallel reducer or authority.
- **Failure behavior:** Duplicate ownership SHALL block architecture acceptance.

### REQ-002 — Ten-invariant crosswalk
- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-010, CUR-004, CUR-005, CUR-006, CUR-009, DER-002`
- **Behavior:** Each of the ten accepted invariants SHALL map to one canonical owner, consumer, physical source seam, and falsifiable acceptance seam; runtime-only gaps SHALL remain explicit.
- **Failure behavior:** Missing, competing, or merely historical ownership SHALL block freeze adoption.

### REQ-003 — Read-only real-PR journey
- **Status:** `SETTLED`
- **Source:** `DEC-002`
- **Behavior:** The product SHALL execute exactly real PR -> exact snapshot -> Acceptance Contract -> clean Python runner -> trusted evidence -> VerificationResult -> CertificationDisposition -> inspectable receipt.
- **Failure behavior:** It SHALL NOT repair, approve, merge, deploy, or call an implementation model.

### REQ-004 — Authenticated live acquisition
- **Status:** `SETTLED`
- **Source:** `DEC-002, DEC-011, CUR-002`
- **Behavior:** Acquisition SHALL authenticate to GitHub when required, but SHALL persist and receipt-bind only a credential-free repository locator identity plus PR number, base/head commits and trees, merge-base policy, immutable diff hash/bytes, changed/deleted paths, checks, pagination completeness, observation time, and freshness/CAS preconditions.
- **Failure behavior:** Caller-supplied structure alone, permission failure, moving head, incomplete data, or identity drift SHALL remain non-certifiable.

### REQ-005 — Version-axis separation
- **Status:** `SETTLED`
- **Source:** `DEC-005, CUR-001, REJ-001`
- **Behavior:** Public protocol and implementation schema SHALL be independently identified, validated, migrated, and receipt-bound; neither SHALL substitute for the other.
- **Failure behavior:** Unknown, mismatched, or stale version identity SHALL never certify.

### REQ-006 — Versioned Acceptance Contract
- **Status:** `SETTLED`
- **Source:** `DEC-002, CUR-004`
- **Behavior:** Every run SHALL bind a complete versioned Acceptance Contract and Verification Plan to the exact PR ChangeSet and required evidence.
- **Failure behavior:** Missing, under-specified, stale, or cross-bound contract/plan SHALL be `UNVERIFIABLE` or rejected according to integrity class.

### REQ-007 — Deterministic Python Verification Profile
- **Status:** `SETTLED`
- **Source:** `DEC-003, DEC-008`
- **Behavior:** V1 SHALL execute only declared adequate deterministic Python witnesses in an isolated clean exact-head environment and capture environment, command, source, exit, stdout/stderr, and artifact identities.
- **Failure behavior:** Inadequate oracle, unavailable runner, nondeterminism, missing binding, or unknown effect SHALL be factual `UNVERIFIABLE` and non-certifiable.

### REQ-008 — Evidence trust and prerequisite provenance
- **Status:** `SETTLED`
- **Source:** `DEC-001, CUR-005, DER-001`
- **Behavior:** Evidence Trust SHALL validate producer/issuer authorization, content/provenance hashes, task/attempt/repository/revision/tree/change/plan/environment binding, freshness, duplicates, replay, and external policy/authority/approval/signing receipts.
- **Failure behavior:** Missing prerequisites SHALL block; malformed, tampered, revoked, stale, or cross-bound evidence SHALL never certify.

### REQ-009 — Deterministic completion and claim ceiling
- **Status:** `SETTLED`
- **Source:** `DEC-003, CUR-006`
- **Behavior:** Completion Core SHALL derive factual `VERIFIED`, `FAILED_VERIFICATION`, or `UNVERIFIABLE`, then a bounded disposition and immutable receipt without caller-minted truth.
- **Failure behavior:** No output may imply approval, merge, deployment, release, production, outcome, or public stability.

### REQ-010 — Durable reconciliation, replay, generation, and CAS
- **Status:** `SETTLED`
- **Source:** `DEC-002, DEC-007, DEC-009, DEC-011, DEC-012, DER-002`
- **Behavior:** Product Runtime SHALL bind idempotency key, canonical request hash, attempt/generation, source snapshot, result/receipt, and ledger generation; ambiguous effects SHALL reconcile before retry and integration subjects SHALL requalify after relevant drift.
- **Failure behavior:** Same key with different request, stale generation, unknown effect, or changed subject SHALL create no duplicate truth and SHALL fail closed.

### REQ-011 — Ledger and signing boundary
- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-009, DEC-011, DEC-012`
- **Behavior:** The carrying layer SHALL append, inspect, replay-verify, recover, and optionally sign exact receipts; signatures attest identity only and SHALL NOT raise the claim ceiling.
- **Failure behavior:** Corruption, truncation, reorder, crash ambiguity, or key mismatch SHALL block signed/durable claims without altering factual verification.

### REQ-012 — Canonical local HTTP and thin clients
- **Status:** `SETTLED`
- **Source:** `DEC-004, DEC-007, CUR-003`
- **Behavior:** One local HTTP contract SHALL own submission/status/result/receipt transport; CLI, MCP, and GitHub Action SHALL call it and SHALL NOT duplicate trust or completion logic.
- **Failure behavior:** Cross-client semantic divergence or direct receipt minting SHALL fail conformance.

### REQ-013 — Packaging and operator journey
- **Status:** `DERIVED`
- **Source:** `DEC-004, CUR-008`
- **Behavior:** Core V1 SHALL install reproducibly with minimal dependencies, offer one certification-first quickstart, preserve receipt compatibility, and mark Workflow OS surfaces legacy/lab until separately retired.
- **Failure behavior:** Failed upgrade SHALL support tested rollback without rewriting receipt history.

### REQ-014 — Protocol maturity and cross-repository trust
- **Status:** `SETTLED`
- **Source:** `DEC-005, DEC-013, CUR-007, DER-003`
- **Behavior:** RC/Stable SHALL require the real vertical, a representative hostile corpus with zero observed high-risk false certifications, a second-repository shadow, client conformance, compatibility, and verified upgrade/rollback evidence.
- **Failure behavior:** Missing oracle, denominator, external subject, compatibility, or gate artifact SHALL preserve the lower protocol maturity and trust claim.

### REQ-015 — Usability and design-partner value
- **Status:** `SETTLED`
- **Source:** `DEC-013`
- **Behavior:** A separate value gate SHALL run a 4–8 week paired evaluation with 3–5 narrow-ICP design partners, measure human verification time including Nexus reading and follow-up overhead, require at least 30% improvement without trust regression, and record a continuation or paid signal.
- **Failure behavior:** Missing paired denominator, human authority, overhead, trust parity, cohort duration, or continuation/paid signal SHALL forbid usability, continuation, paid, or commercial-value claims without lowering protocol truth.

## 14. Behavioral and interface decisions

Per `DEC-007`, the canonical HTTP surface is `POST /v1/certifications`, `GET /v1/certifications/{request_id}`, `GET /v1/certifications/{request_id}/receipt`, and `POST /v1/receipts/verify`, bound only to `127.0.0.1` with a per-install bearer token from an OS-protected source. Request identity includes independent protocol/schema axes, repository/PR, expected base/head/freshness, Acceptance Contract, Verification Plan, `python-oci-pytest-v1`, and idempotency key. Response separates acquisition, execution, evidence, factual verification, disposition, reasons, receipt, and claim ceiling. Exact replay returns the same run; changed request, stale generation/source, or unknown effect fails closed and reconciles durable SQLite state before retry. Receipt verification states `ENVELOPE_ONLY` unless stored original inputs permit full recomputation.

## 15. Verification seam

Highest pre-Stable seam: live read-only GitHub acquisition, isolated exact-head Python execution, trusted ingestion, core hostile tests, crash/restart/idempotency reconciliation, receipt replay, HTTP/client conformance, clean install/rollback, representative benchmark, and non-Nexus shadow.

## 16. Acceptance criteria

### AC-001 — Unique invariant ownership
- **Requirement:** `REQ-001`
- **Evidence level:** `STATIC`
- **Verification seam:** owner/source/consumer/test crosswalk plus duplicate-reducer scan
- **Pass:** all ten invariants have one canonical owner and an adequate falsification seam.
- **Negative control:** introduce/detect caller-minted or parallel reducer authority.
- **Fail:** any invariant is missing, duplicated, or claimed only by prose.
- **Receipt binding:** spec, crosswalk, source commit/tree, and test-report hashes

### AC-002 — Exact authenticated PR snapshot
- **Requirement:** `REQ-004`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** live acquisition followed by independent identity re-read
- **Pass:** repository/PR/base/head/tree/diff/path/check identities remain exact and provenance-bound.
- **Negative control:** move head, truncate pagination, substitute diff/tree/repository, or use caller-only object.
- **Fail:** stale/incomplete/untrusted snapshot reaches Evidence Trust as trusted.
- **Receipt binding:** acquisition method, repository locator hash, PR, commit/tree/diff/check hashes, observation time

### AC-003 — Version-axis binding
- **Requirement:** `REQ-005`
- **Evidence level:** `SIMULATION`
- **Verification seam:** protocol/schema/contract/plan compatibility and stale-version matrix
- **Pass:** both version axes and contract subjects are explicit and independently validated.
- **Negative control:** swap public protocol with implementation schema or replay another contract/plan.
- **Fail:** ambiguous/mismatched version or contract can certify.
- **Receipt binding:** protocol, schema, contract, plan, ChangeSet, and compatibility hashes

### AC-004 — Python oracle truth table
- **Requirement:** `REQ-007`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** clean exact-head runner with adequate pass, adequate fail, inadequate, unavailable, and nondeterministic witnesses
- **Pass:** adequate pass -> `VERIFIED`; adequate fail -> `FAILED_VERIFICATION`; all inadequate/unknown cases -> `UNVERIFIABLE`.
- **Negative control:** replay artifact from another command/environment/source/attempt.
- **Fail:** inadequate oracle reaches highest certification.
- **Receipt binding:** profile, environment, source, command, output, exit, artifact, and oracle hashes

### AC-005 — Trusted evidence and prerequisite separation
- **Requirement:** `REQ-008`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** ingestion/prerequisite hostile matrix
- **Pass:** producer, issuer, subject, time, action, decision, signature-receipt, and evidence identities all validate.
- **Negative control:** tamper, duplicate, expire, revoke, reorder, or cross-bind each identity class.
- **Fail:** hostile or unauthenticated evidence can certify.
- **Receipt binding:** context/profile/bundle/ingestion/external-receipt/prerequisite hashes

### AC-006 — Completion and claim ceiling
- **Requirement:** `REQ-009`
- **Evidence level:** `SIMULATION`
- **Verification seam:** reducer truth table, receipt recomputation, and caller-forgery probes
- **Pass:** output is deterministic and never exceeds factual certification.
- **Negative control:** inject verification/disposition/policy/receipt hash or forbidden higher claim.
- **Fail:** caller truth or authority escalation survives.
- **Receipt binding:** contract/change/plan/evidence/result/disposition/receipt hashes

### AC-007 — Retry/replay/CAS/requalification
- **Requirement:** `REQ-010`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** crash, disconnect, duplicate request, request drift, generation drift, and integration-subject drift tests
- **Pass:** exact replay is idempotent; ambiguous effect reconciles; changed request/subject/generation fails closed.
- **Negative control:** crash at every durable boundary and retry before/after source drift.
- **Fail:** duplicate or stale truth is created.
- **Receipt binding:** idempotency, request, attempt, generation, source snapshot, result, receipt, ledger hashes

### AC-008 — Ledger recovery and signature
- **Requirement:** `REQ-011`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** append/read/restart/replay with corruption and key-metadata probes
- **Pass:** exact receipt identity survives restart and optional signature verifies without claim elevation.
- **Negative control:** truncate, reorder, replace, duplicate, crash, or rotate key metadata.
- **Fail:** ledger/signing hides ambiguity or raises authority.
- **Receipt binding:** ledger generation/entry, receipt, signer/key metadata, recovery observation

### AC-009 — Canonical HTTP tracer bullet
- **Requirement:** `REQ-012`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** one local HTTP request from authenticated PR acquisition through receipt inspection
- **Pass:** HTTP returns the exact acquisition, runner, evidence, verification, disposition, and receipt subjects without duplicating core semantics.
- **Negative control:** idempotency/request/version drift, interrupted request, and direct caller-minted result cannot create a second result.
- **Fail:** HTTP bypasses either core, duplicates semantics, or loses subject/reconciliation binding.
- **Receipt binding:** canonical request, idempotency, run, acquisition, evidence, result, response, and receipt hashes

### AC-010 — Cross-repository trust gate
- **Requirement:** `REQ-014`
- **Evidence level:** `BENCHMARK`
- **Verification seam:** representative hostile corpus and second-repository shadow
- **Pass:** corpus and shadow are revision-bound, contain at least 50 cases across at least 8 hostile families, and record zero observed high-risk false certifications with the exact denominator.
- **Negative control:** remove oracle, denominator, hostile-family coverage, external repository/revision, or shadow artifact.
- **Fail:** internal source/tests or the fixed local corpus are promoted to cross-repository or Stable truth.
- **Receipt binding:** protocol candidate, corpus/task-set, external repository/revision, attempts, oracle, denominator, and shadow-report hashes

### AC-011 — Thin-client semantic parity
- **Requirement:** `REQ-012`
- **Evidence level:** `CANARY`
- **Verification seam:** CLI, MCP, and GitHub Action conformance against the same canonical HTTP request
- **Pass:** every client calls HTTP and returns a canonically equivalent result/receipt without local trust or completion logic.
- **Negative control:** replace HTTP response, attempt direct receipt minting, or introduce client-only disposition logic.
- **Fail:** any client becomes a parallel semantic owner.
- **Receipt binding:** client artifact, canonical request/response, protocol/schema, and receipt hashes

### AC-012 — Install, upgrade, and rollback journey
- **Requirement:** `REQ-013`
- **Evidence level:** `CANARY`
- **Verification seam:** clean-environment install, certification-first quickstart, compatible upgrade, and rollback
- **Pass:** installation runs the HTTP journey; upgrade preserves readable receipts; rollback restores the prior runtime without rewriting history.
- **Negative control:** incompatible protocol/ledger or missing prior receipt reader is refused rather than coerced.
- **Fail:** legacy orchestration CLI is required or receipt history becomes unreadable.
- **Receipt binding:** package/artifact, environment, protocol/ledger versions, quickstart, upgrade, rollback, and canary hashes

### AC-013 — Ten-invariant crosswalk completeness
- **Requirement:** `REQ-002`
- **Evidence level:** `STATIC`
- **Verification seam:** the physical ten-row owner/source/consumer/witness/coverage/gap table plus duplicate-owner scan
- **Pass:** every accepted invariant has exactly one canonical owner, a consumer, current source classification, falsifiable witness, and explicit product gap.
- **Negative control:** remove one row/owner/witness or introduce a competing truth owner.
- **Fail:** crosswalk coverage is incomplete, ambiguous, or based only on historical prose.
- **Receipt binding:** spec, crosswalk, source commit/tree, and static-audit hashes

### AC-014 — Complete read-only Golden Path
- **Requirement:** `REQ-003`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** one real PR traverses acquisition, contract, runner, trust, completion, ledger, and HTTP receipt inspection without repository mutation
- **Pass:** the exact journey completes with revision-bound evidence and a bounded receipt.
- **Negative control:** attempt repair, approval, merge, deploy, model invocation, or bypass of any stage.
- **Fail:** the journey mutates the subject or silently substitutes an internal lifecycle result.
- **Receipt binding:** repository/PR, acquisition, contract, runner, evidence, verification, disposition, ledger, HTTP, and receipt hashes

### AC-015 — Acceptance Contract and Verification Plan binding
- **Requirement:** `REQ-006`
- **Evidence level:** `SIMULATION`
- **Verification seam:** contract/plan/ChangeSet/evidence subject matrix and stale/cross-bound replay probes
- **Pass:** exact versioned contract and plan bind all required verifier and scope identities.
- **Negative control:** omit, under-specify, reorder incompatibly, or replay a contract/plan from another subject.
- **Fail:** missing, stale, or cross-bound contract/plan can certify.
- **Receipt binding:** contract, plan, ChangeSet, evidence requirement, protocol, and schema hashes

### AC-016 — Public protocol maturity gate
- **Requirement:** `REQ-014`
- **Evidence level:** `BENCHMARK`
- **Verification seam:** public protocol compatibility, client conformance, upgrade, and rollback after the real vertical and external shadow
- **Pass:** every RC/Stable input is revision-bound and explicit RC/Stable thresholds pass without inferred release or production authority.
- **Negative control:** remove compatibility, client conformance, upgrade, rollback, real-vertical, or shadow evidence.
- **Fail:** corpus/shadow or source-only evidence is promoted to Stable, release, production, or value truth.
- **Receipt binding:** protocol candidate, compatibility matrix, conformance, upgrade/rollback, tracer-bullet, corpus, shadow, and report hashes

### AC-017 — Paired usability and commercial-value gate
- **Requirement:** `REQ-015`
- **Evidence level:** `BENCHMARK`
- **Verification seam:** 4–8 week paired human verification-time experiment with 3–5 narrow-ICP design partners after the protocol maturity gate
- **Pass:** paired measurements show at least 30% improvement including Nexus reading/follow-up overhead, no trust regression, and a continuation or paid signal.
- **Negative control:** remove the paired denominator, human authority, overhead, trust comparison, cohort/duration evidence, or continuation/paid signal.
- **Fail:** protocol maturity or unpaired anecdotes are promoted to usability, continuation, paid, or commercial truth.
- **Receipt binding:** design-partner/cohort identity, paired subjects/attempts, human authority, oracle, time log, overhead, trust comparison, continuation/paid signal, and report hashes

## 17. Traceability matrix

| Requirement | Sources | Delta | Acceptance | Evidence level | Claim ceiling | Task-card handoff group |
|---|---|---|---|---|---|---|
| REQ-001 | DEC-001,DEC-006,CON-001,DER-001 | MODIFIED | AC-001 | STATIC | boundary candidate | TG-0 |
| REQ-002 | DEC-001,DEC-010,CUR-004,CUR-005,CUR-006,CUR-009,DER-002 | MODIFIED | AC-013 | STATIC | crosswalk only | TG-0 |
| REQ-003 | DEC-002 | ADDED | AC-014 | LIVE_RUNTIME | tracer bullet | TG-5 |
| REQ-004 | DEC-002,DEC-011,CUR-002 | ADDED | AC-002 | LIVE_RUNTIME | trusted snapshot | TG-1 |
| REQ-005 | DEC-005,CUR-001,REJ-001 | MODIFIED | AC-003 | SIMULATION | version contract | TG-0 |
| REQ-006 | DEC-002,CUR-004 | MODIFIED | AC-015 | SIMULATION | contract bound | TG-0/TG-2 |
| REQ-007 | DEC-003,DEC-008 | ADDED | AC-004 | LIVE_RUNTIME | Python profile | TG-2 |
| REQ-008 | DEC-001,CUR-005,DER-001 | MODIFIED | AC-005 | LIVE_RUNTIME | trusted evidence | TG-3 |
| REQ-009 | DEC-003,CUR-006 | MODIFIED | AC-006 | SIMULATION | factual completion | TG-0/TG-5 |
| REQ-010 | DEC-002,DEC-007,DEC-009,DEC-011,DEC-012,DER-002 | ADDED | AC-007 | LIVE_RUNTIME | durable runtime | TG-4 |
| REQ-011 | DEC-001,DEC-009,DEC-011,DEC-012 | ADDED | AC-008 | LIVE_RUNTIME | ledger candidate | TG-4 |
| REQ-012 | DEC-004,DEC-007,CUR-003 | ADDED | AC-009,AC-011 | LIVE_RUNTIME | HTTP/client parity | TG-5/TG-6 |
| REQ-013 | DEC-004,CUR-008 | MODIFIED | AC-012 | CANARY | operator journey | TG-6 |
| REQ-014 | DEC-005,DEC-013,CUR-007,DER-003 | ADDED | AC-010,AC-016 | BENCHMARK | cross-repo trust/protocol maturity | TG-7/TG-8 |
| REQ-015 | DEC-013 | ADDED | AC-017 | BENCHMARK | bounded usability/value evidence | TG-9 |

## 18. Evidence and claim ceiling

Current evidence supports only `EXPERIMENTAL_LIBRARY_KERNEL_AND_TRUST_FOUNDATION_SOURCE_VERIFIED_AT_785751e1` and a review-backed spec candidate. It does not support live acquisition, Product Runtime, ledger, cross-repo value, Stable, release, production, or commercial claims.

## 19. Rollback and failure handling

All subject-repository interaction is read-only. Unknown effects reconcile by durable identity before retry. Version/runtime upgrades preserve append-only receipts and a tested reader/rollback. No failure path may lower trust, reuse cross-bound evidence, mutate the PR, or convert unknown to success.

## 20. Documentation and learning write-back

After adoption, product protocol, operator quickstart, compatibility, and legacy/lab boundaries require separate Task Cards. Learning may record evidence but cannot promote product or trust policy.

## 21. Risks and unknowns

The former HTTP, runner, ledger/signing, old-card, operational-default, rollback-claim, protocol/value split, and pilot-threshold unknowns are resolved by `DEC-007` through `DEC-013`; implementation still must prove their acceptance criteria. External-repository and design-partner selection are execution evidence owned by TG-7 and TG-9. Additional risks: trusted source mistaken for live acquisition; fixed corpus overclaimed; adapter/core ownership blurred; legacy orchestration retained as hidden dependency; OCI and bearer-token setup increasing operator friction.

## 22. Unresolved owner decisions

none

## 23. Task-card handoff boundary

| Task group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker |
|---|---|---|---|---|---|---|---|---|---|
| TG-0 Boundary/version/crosswalk freeze | REQ-001;REQ-002;REQ-005;REQ-006;REQ-009 | AC-001;AC-003;AC-006;AC-013;AC-015 | adopted two-core/version/invariant contract plus additive old-card reconciliation | DEC-007 through DEC-013 | static + simulation | `CORE_V1_BOUNDARY_ADOPTED` | medium | not applicable | none |
| TG-1 Live GitHub acquisition | REQ-004 | AC-002 | authenticated immutable PR snapshot | TG-0 | live read-only probes | `LIVE_PR_SNAPSHOT_VERIFIED` | medium | not applicable | none |
| TG-2 Python profile | REQ-007 | AC-004 | clean deterministic witness bundle | TG-0 accepted contract | isolated runner matrix | `PYTHON_PROFILE_VERIFIED` | medium | not applicable | none |
| TG-3 Evidence Trust extraction | REQ-008 | AC-005 | canonical trust owner consumes TG-1/TG-2 | TG-1 + TG-2 accepted receipts | hostile ingestion tests | `EVIDENCE_TRUST_BOUNDARY_VERIFIED` | medium | not applicable | none |
| TG-4 Durable ledger/reconciliation | REQ-010;REQ-011 | AC-007;AC-008 | idempotent crash-safe receipt history | TG-3 accepted identities | restart/tamper/CAS | `LOCAL_LEDGER_RECONCILIATION_VERIFIED` | medium | not applicable | none |
| TG-5 HTTP tracer bullet | REQ-003;REQ-012 | AC-009;AC-014 | real PR to inspectable receipt | TG-1 + TG-2 + TG-3 + TG-4 accepted interfaces | live local E2E plus upstream witness consumption | `REAL_PR_TRACER_BULLET_VERIFIED` | medium | not applicable | none |
| TG-6 Thin clients/package | REQ-012;REQ-013 | AC-011;AC-012 | client parity and clean install journey | TG-5 | conformance/install/rollback | `OPERATOR_JOURNEY_VERIFIED` | medium | not applicable | none |
| TG-7 Corpus/second repo | REQ-014 | AC-010 | representative corpus and external shadow | TG-5 plus DER-003 selection | benchmark + shadow | `CROSS_REPO_TRUST_SHADOW_VERIFIED` | medium | not applicable | none |
| TG-8 Protocol maturity | REQ-014 | AC-016 | evidence-gated RC/Stable readiness | TG-6 + TG-7 | compatibility/conformance/upgrade/rollback | bounded protocol-maturity claim | medium | not applicable | none |
| TG-9 Design-partner value | REQ-015 | AC-017 | paired usability and continuation/paid evidence | TG-8 | 3–5 partner, 4–8 week paired experiment | bounded usability/value claim | medium | not applicable | none |
After TG-0, TG-1 and TG-2 may run in parallel in isolated worktrees. TG-3 consumes both accepted evidence contracts. TG-4 follows frozen TG-3 identities. TG-5 integrates. TG-6 and TG-7 may then run in parallel. TG-8 joins their accepted evidence; TG-9 follows TG-8.

TG-7 covers the representative corpus and second-repository shadow; TG-8 is the Protocol RC/Stable readiness witness; TG-9 independently measures usability and commercial-value signals. `DER-003` makes selection part of those future tasks and forbids cross-repo, Stable, or value claims until their respective physical evidence exists.

## 24. Out of scope

No source implementation, Task Card creation, Candidate, approval, merge, deployment, release, production claim, partner outreach, or deletion is authorized by this document.

## 25. Supersession and change history

- Drafted 2026-09-04 from Owner planning direction, exact current source, coordinator tests, C5 Spark review, B7 Luna review, and bounded A4 Opus partial crosswalk.
- Corrects the false equation between public protocol v1 and internal implementation schema v2.
- Owner adopted `DEC-007` through `DEC-010` on 2026-09-04, then confirmed the operational defaults and protocol/value separation in `DEC-011` through `DEC-013`. The old Local ChangeSet card remains physically unchanged until TG-0 performs additive formal reconciliation.
