# External Verified Candidate Adoption Repair — Execution Projection

- **Spec ID:** `SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001`
- **Status:** `READY_FOR_TASK_CARDS`
- **Basis snapshot:** Original approved spec `SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-001` SHA-256 `f1e793017b1335ccd262294d53d10405465015cbeda2b74c3124a5f320f69b1b`; Owner master authorization SHA-256 `1adad9c3cc0356c6bd7d7babf41bf980664c3ed38253909642b78e4992572133`; contract base `a33fbd65b21ddf67085be9fa4ea245f59626ddd8`; accepted EPB Candidate `b3343c95479f03857af7761381a1b839ac049e24`
- **Supersedes:** none; execution projection only
- **Claim ceiling:** Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim.

## 1. Problem statement

The exact independently accepted EPB external-bootstrap Candidate has no durable lifecycle task. Current lifecycle approval requires a persisted promotion packet, Candidate state hash, and lifecycle-native verified receipt, while current source has no typed external Candidate adoption seam.

## 2. Desired outcome

A distinct fail-closed lifecycle action physically re-verifies one exact immutable precommitted external-bootstrap Candidate and atomically creates ordinary pending-approval state without running an implementation worker, rewriting the Candidate, approving it, or integrating it.

## 3. Basis, coverage, and freshness

This execution projection preserves the exact original approved specification and Owner authorization identities above. It resolves only the document-state and one-acceptance-to-one-requirement compiler constraints. No Product, trust, Task4, signing, release, production, or Candidate semantics are changed.

## 4. Source and decision ledger

| ID | Class | Statement | Authority/location | Freshness/snapshot | Status | Limitation |
|---|---|---|---|---|---|---|
| `DEC-001` | DEC | Preserve exact EPB Candidate without rewrite or substitution. | Original approved spec plus Owner master authorization | Current mission | BINDING | none |
| `DEC-002` | DEC | Adoption ends at pending approval; unchanged approval and integration remain separate. | Owner master authorization | Current mission | BINDING | none |
| `DEC-003` | DEC | Same-mission repair and Task Card compilation are authorized; Task4/release/production remain forbidden. | Owner master authorization | Current mission | BINDING | none |
| `CUR-001` | CUR | `TASK-EPB-001-R1` is absent from durable lifecycle state. | canonical lifecycle query | 2026-08-30 | EVIDENCE | exact state root only |
| `CUR-002` | CUR | Candidate/tree/base/diff/card/validation identities are exact. | Git objects and immutable artifacts | 2026-08-30 | EVIDENCE | local evidence roots |
| `CUR-003` | CUR | Current source has approve/bind/integrate but no external Candidate adoption action. | committed lifecycle/Gateway/CLI source | contract base | EVIDENCE | bounded source audit |
| `CUR-004` | CUR | Historical validation receipt is not lifecycle-native `VerifiedCandidateReceipt`. | receipt SHA-256 `8c9978...` | immutable | EVIDENCE | requires physical lifecycle verification |
| `CON-001` | CON | Approval binds exact Candidate commit/tree/state/verified receipt. | rollback runbook and lifecycle source | current | BINDING | none |
| `CON-002` | CON | Lifecycle state may not be hand-edited and downstream authorities remain separate. | root AGENTS and Task Execution Contract | current | BINDING | none |
| `REJ-001` | REJ | Do not reuse failed `TASK-EPB-001` negative evidence or hand-mint promotion state. | R1 card and Owner authorization | current | REJECTED | none |

## 5. Current verified state

The immutable EPB Candidate remains accepted. The only in-scope defect is the missing lifecycle-native adoption transition and evidence binding.

## 6. Owner decisions

- Preserve exact Candidate and accepted claim ceiling (`DEC-001`).
- Implement the same-mission adoption repair and continue only after independent acceptance (`DEC-002`, `DEC-003`).

## 7. Canonical terminology

- **Adoption:** physical verification and durable pending-approval binding of an existing immutable Candidate; never approval or integration.
- **Lifecycle-native verification:** existing CandidateVerifier/Committer semantics applied to a clean exact-base/exact-Candidate Target, producing a normal verified receipt and promotion packet.

## 8. Change delta

Mode: BROWNFIELD

Baseline: committed lifecycle/Gateway/CLI source at `a33fbd65b21ddf67085be9fa4ea245f59626ddd8` plus original approved specification SHA-256 `f1e793017b1335ccd262294d53d10405465015cbeda2b74c3124a5f320f69b1b`.

### ADDED

One typed `CANDIDATE_ADOPT_EXTERNAL` action, atomic adoption receipt/state transition, and hostile controls.

### MODIFIED

Lifecycle gains one absent-state predecessor into ordinary pending approval. Downstream approval/integration contracts remain unchanged.

### REMOVED

None.

### RENAMED

None.

## 9. Scope

Lifecycle action contract, durable task service, unified Gateway action/schema, CLI compatibility, rollback runbook, and focused behavioral tests.

## 10. Non-goals

No arbitrary SHA trust import; Candidate rewrite; implementation-worker execution during adoption; approval; integration; push; Task4; trust root; signing; Product semantics; release; deployment; production; or public-stability claim.

## 11. User and operator stories

1. A controller submits one exact Owner-bound immutable Candidate adoption action.
2. Exact physical evidence yields one pending-approval Candidate state.
3. Any substitution or replay drift fails without promotable partial state.

## 12. Architecture and authority boundaries

`Owner-bound typed adoption -> physical Git/artifact verification -> existing CandidateVerifier -> existing CandidateCommitter precommitted reuse -> atomic pending-approval state -> unchanged approval/integration`.

Adoption creates no new trust, approval, integration, Planner, Product, or certification authority.

## 13. Requirements

### REQ-001 — Distinct typed adoption authority

- **Status:** `SETTLED`
- **Source:** `DEC-002, DEC-003, CUR-003, CON-002`
- **Behavior:** The system SHALL expose a closed `CANDIDATE_ADOPT_EXTERNAL` action requiring fresh one-shot Owner authority bound to task, attempt, contract/card, Candidate, base, diff, validation, acceptance, runtime, root, and branch identities.
- **Failure behavior:** Missing, expired, replayed, malformed, or mismatched authority SHALL fail before state creation.
- **Rationale:** Adoption is distinct from approval.
- **Authority/interface:** lifecycle Gateway and action contract
- **Non-goal linkage:** Section 10

### REQ-002 — Exact immutable subject validation

- **Status:** `SETTLED`
- **Source:** `DEC-001, CUR-002, CON-001`
- **Behavior:** The system SHALL physically resolve and rehash the exact Candidate, tree, base ancestry, base-to-Candidate diff, Task Card, validation receipt, and independent acceptance artifact.
- **Failure behavior:** Any object/artifact absence, mismatch, path escape, symlink substitution, or wrong repository/task SHALL fail closed.
- **Rationale:** Prevent caller-minted identity.
- **Authority/interface:** adoption service
- **Non-goal linkage:** Section 10

### REQ-003 — No worker and no Candidate mutation

- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-003`
- **Behavior:** Adoption SHALL NOT invoke an implementation worker/provider or modify, wrap, amend, rebase, squash, cherry-pick, patch, or replace the Candidate.
- **Failure behavior:** Any attempted worker dispatch or Candidate mutation SHALL abort.
- **Rationale:** Preserve accepted subject.
- **Authority/interface:** adoption executor
- **Non-goal linkage:** Section 10

### REQ-004 — Lifecycle-native verification

- **Status:** `SETTLED`
- **Source:** `CUR-004, CON-001, DEC-002`
- **Behavior:** The action SHALL run the existing Candidate verification contract on a clean exact-base/exact-Candidate snapshot, deriving `candidate_state_hash` and lifecycle-native `VerifiedCandidateReceipt`; historical validation/acceptance remain cross-checked inputs, never substituted verifier truth.
- **Failure behavior:** Verification, environment, changed-path, dirty-state, or evidence inconsistency SHALL leave no promotable state.
- **Rationale:** Historical receipt schema is not lifecycle-native.
- **Authority/interface:** existing CandidateVerifier
- **Non-goal linkage:** Section 10

### REQ-005 — Atomic durable adoption

- **Status:** `SETTLED`
- **Source:** `CUR-001, CON-001, CON-002, REJ-001, DEC-002`
- **Behavior:** After all gates pass, the action SHALL atomically create one task attempt, durable Candidate/ref evidence, promotion packet, Candidate state hash, verified-receipt hash, acceptance binding, adoption receipt, and `PENDING_HUMAN_APPROVAL` status.
- **Failure behavior:** Existing task collision, concurrency drift, partial write, or post-check mismatch SHALL fail closed.
- **Rationale:** Existing approval requires these bindings.
- **Authority/interface:** self-hosted lifecycle state
- **Non-goal linkage:** Section 10

### REQ-006 — Idempotency and reconciliation

- **Status:** `SETTLED`
- **Source:** `CON-002, DEC-002`
- **Behavior:** Exact replay SHALL return the original adoption receipt; any input drift under reused action/approval/idempotency identity SHALL fail; timeout/disconnect SHALL reconcile before retry.
- **Failure behavior:** Duplicate or split-brain state SHALL never be admitted.
- **Rationale:** Preserve one durable truth.
- **Authority/interface:** Gateway and durable service
- **Non-goal linkage:** none

### REQ-007 — Unchanged downstream gates

- **Status:** `SETTLED`
- **Source:** `DEC-002, DEC-003, CON-001`
- **Behavior:** Adoption SHALL end at pending approval; existing approval, integration, push, release, activation, and public-claim gates remain unchanged and separately required.
- **Failure behavior:** Downstream fields or effects in adoption SHALL be rejected.
- **Rationale:** Preserve authority separation.
- **Authority/interface:** lifecycle state machine
- **Non-goal linkage:** Section 10

## 14. Behavioral and interface decisions

Only `ABSENT + exact external-bootstrap evidence + one-shot adoption authority -> ADOPTING -> PENDING_HUMAN_APPROVAL` is added. Failed predecessor state cannot be renamed or reused.

## 15. Verification seam

Real clean exact-base/exact-Candidate Git snapshot plus actual service/Gateway action, physical verifier execution, durable-state inspection, Git before/after audit, worker-dispatch spy, and hostile replay/concurrency controls.

## 16. Acceptance criteria

### AC-001 — Typed authority binding

- **Requirement:** `REQ-001`
- **Evidence level:** `CANARY`
- **Verification seam:** real Gateway handler and one-shot approval validation
- **Pass:** Exact authority is accepted only for the exact adoption action.
- **Negative control:** expired, replayed, wrong action/runtime/card/Candidate authority fails.
- **Fail:** state is written from invalid authority.
- **Receipt binding:** action, attempt, task/card, Candidate, runtime hashes

### AC-002 — No worker or rewrite

- **Requirement:** `REQ-003`
- **Evidence level:** `CANARY`
- **Verification seam:** Git before/after audit and worker/provider invocation spy
- **Pass:** Candidate SHA/tree unchanged and invocation count zero.
- **Negative control:** attempted worker dispatch or wrapper commit fails.
- **Fail:** any implementation execution or replacement commit occurs.
- **Receipt binding:** Candidate SHA/tree and action ID

### AC-003 — Replay and concurrency

- **Requirement:** `REQ-006`
- **Evidence level:** `SIMULATION`
- **Verification seam:** concurrent/replayed Gateway calls against one isolated durable state root
- **Pass:** exact replay is idempotent and drift is rejected.
- **Negative control:** reused identity with changed Candidate/receipt/acceptance fails.
- **Fail:** duplicate/split state appears.
- **Receipt binding:** request hash, action, attempt, idempotency identities

### AC-004 — Downstream separation

- **Requirement:** `REQ-007`
- **Evidence level:** `CANARY`
- **Verification seam:** post-adoption lifecycle/Git/network inspection
- **Pass:** pending approval only; no downstream authority/effect consumed.
- **Negative control:** downstream fields are schema-rejected.
- **Fail:** adoption approves, integrates, pushes, releases, or activates.
- **Receipt binding:** adoption receipt and task-action envelope

### AC-005 — Physical subject binding

- **Requirement:** `REQ-002`
- **Evidence level:** `CANARY`
- **Verification seam:** real Git objects and immutable artifacts
- **Pass:** commit/tree/base/diff/card/validation/acceptance all rehash and agree.
- **Negative control:** independently substitute each identity or artifact.
- **Fail:** any mismatch reaches durable state.
- **Receipt binding:** all subject/artifact hashes

### AC-006 — Lifecycle-native verifier receipt

- **Requirement:** `REQ-004`
- **Evidence level:** `CANARY`
- **Verification seam:** real CandidateVerifier on clean precommitted Target
- **Pass:** physical verifier evidence derives exact state hash and lifecycle-native receipt.
- **Negative control:** caller-supplied state/receipt or validation-receipt substitution fails.
- **Fail:** unverified or caller-minted receipt becomes promotable.
- **Receipt binding:** Candidate state and verified-receipt hashes

### AC-007 — Atomic pending state

- **Requirement:** `REQ-005`
- **Evidence level:** `CANARY`
- **Verification seam:** actual durable service with fault/collision/concurrency controls
- **Pass:** exactly one complete pending-approval state is committed after every gate.
- **Negative control:** collision, partial fault, or concurrent drift leaves no promotable partial state.
- **Fail:** malformed/partial/duplicate state is visible.
- **Receipt binding:** task/attempt/promotion/adoption identities

## 17. Traceability matrix

| Requirement | Sources | Delta | Acceptance | Evidence level | Claim ceiling | Task-card handoff group |
|---|---|---|---|---|---|---|
| `REQ-001` | `DEC-002, DEC-003, CUR-003, CON-002` | ADDED | `AC-001` | CANARY | Typed adoption action exists | External Candidate adoption repair |
| `REQ-002` | `DEC-001, CUR-002, CON-001` | ADDED | `AC-005` | CANARY | Exact subject is validated | External Candidate adoption repair |
| `REQ-003` | `DEC-001, DEC-003` | ADDED | `AC-002` | CANARY | No worker/rewrite occurred | External Candidate adoption repair |
| `REQ-004` | `CUR-004, CON-001, DEC-002` | ADDED | `AC-006` | CANARY | Lifecycle-native evidence exists | External Candidate adoption repair |
| `REQ-005` | `CUR-001, CON-001, CON-002, REJ-001, DEC-002` | ADDED | `AC-007` | CANARY | One pending Candidate state exists | External Candidate adoption repair |
| `REQ-006` | `CON-002, DEC-002` | ADDED | `AC-003` | SIMULATION | Replay is bounded | External Candidate adoption repair |
| `REQ-007` | `DEC-002, DEC-003, CON-001` | MODIFIED | `AC-004` | CANARY | Downstream authority remains separate | External Candidate adoption repair |

## 18. Evidence and claim ceiling

Only the adoption capability may be claimed independently verified. Original EPB adoption, approval, integration, remote merge, release, production, Task4, and public stability remain later evidence subjects.

## 19. Rollback and failure handling

Pre-commit failure leaves no task state. Post-adoption failures preserve Candidate/ref/receipts for status and reconciliation. No automatic cleanup.

## 20. Documentation and learning write-back

After acceptance, update the existing rollback runbook only; create no parallel authority guide.

## 21. Risks and unknowns

No unresolved Owner decision. Implementation must still prove precommitted CandidateVerifier compatibility, atomic absent-state creation, closed schema, and no-worker behavior.

## 22. Unresolved owner decisions

none

## 23. Task-card handoff boundary

| Task group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker |
|---|---|---|---|---|---|---|---|---|---|
| External Candidate adoption repair | `REQ-001`; `REQ-002`; `REQ-003`; `REQ-004`; `REQ-005`; `REQ-006`; `REQ-007` | `AC-001`; `AC-002`; `AC-003`; `AC-004`; `AC-005`; `AC-006`; `AC-007` | Typed fail-closed external Candidate adoption reaches pending approval only | Existing CandidateVerifier and durable lifecycle | Real immutable precommitted Candidate plus Gateway/service hostile tests | Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim. | medium | CANDIDATE | none |

## 24. Out of scope

Original EPB approval/integration/remote merge until this repair is independently accepted; Task4; trust/signing; release; deployment; production; public stability.

## 25. Supersession and change history

Execution projection of original approved spec SHA-256 `f1e793...`, structurally refined under Owner master authorization SHA-256 `1adad9...`. It does not replace or rewrite the original approved artifact.
