# Product Kernel Usability Repair Implementation Plan

> **For agentic workers:** REQUIRED: Use the available `subagent-driven-development` workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimum provider-neutral trusted ingestion and provenance seam that reduces repeated human evidence inspection without weakening the existing Completion Certification reducers or rewriting the immutable 20-case validation truth.

**Architecture:** Raw, pre-materialized evidence is admitted only through a structural/content-addressed provenance validator. Successful admission creates the existing `EvidenceBundle`; separately validated prerequisite provenance is converted to the existing internal policy booleans only inside a trusted adapter, which calls the unchanged Product Kernel and wraps its core receipt. Legacy narrative evidence never enters the typed PASS path.

**Tech Stack:** Python 3.14, frozen dataclasses/enums, canonical SHA-256 hashing, existing Product Kernel APIs, pytest, Ruff, Pyright.

---

## Frozen API and trust contract

### `product/evidence/ingestion.py`

The RED tests define these exact provider-neutral values:

- `EvidenceType`: `VERIFIER_RESULT`, `CI_CHECK`, `MANUAL_REVIEW`, `RUNTIME_OBSERVATION`, `LEGACY_RECORD`.
- `ProducerRole`: `VERIFIER`, `CI`, `REVIEWER`, `OWNER`, `SIGNER`, `RUNTIME`.
- `EvidenceGeneration`: `SOURCE`, `EXECUTION`, `RUNTIME`, `LEGACY_NARRATIVE`.
- `FreshnessStatus`: `SOURCE_ALIGNED`, `SOURCE_AHEAD_OF_RUNTIME`, `RUNTIME_IDENTITY_MISMATCH`, `STALE_OBSERVATION`, `READY_IDENTITY_BOUND`, `CONVERGENCE_UNKNOWN`.
- `TrustRole`: `POLICY`, `AUTHORITY`, `APPROVAL`, `SIGNING`; `TrustDecision`: `ALLOW`, `DENY`.
- `ProducerGrant(producer_id: str, role: ProducerRole, software_hash: str, verification_methods: tuple[str, ...])`.
- `IssuerGrant(issuer_id: str, roles: tuple[TrustRole, ...], actions: tuple[str, ...], verification_methods: tuple[str, ...])`.
- `IngestionProfile(profile_id: str, producers: tuple[ProducerGrant, ...], issuers: tuple[IssuerGrant, ...], max_age_seconds: int)` with a canonical `hash`.
- `EvidenceRequirement(verifier_id: str, artifact_id: str, evidence_type: EvidenceType, generation: EvidenceGeneration, producer_id: str, execution_id: str, attempt_id: str, environment_hash: str, content_hash: str, provenance_hash: str, runtime_ready_required: bool, human_semantic_review_required: bool)`; the independently compiled requirement, not the submission, supplies both expected hashes.
- `RuntimeSourceObservation(generation: EvidenceGeneration, desired_source_revision: str, loaded_source_revision: str, expected_runtime_identity: str | None, observed_runtime_identity: str | None, desired_generation: int, observed_generation: int, observed_at: str, expires_at: str, readiness_status: str | None)`; its constructor accepts only `SOURCE` or `RUNTIME` and rejects `EXECUTION`/`LEGACY_NARRATIVE` with `ValueError`.
- `ProvenanceEnvelope(schema: str, evidence_id: str, evidence_type: EvidenceType, verifier_id: str, artifact_id: str, producer_id: str, producer_role: ProducerRole, producer_software_hash: str, repository_id: str, source_revision: str, source_tree: str, target_revision: str, target_tree: str, change_set_hash: str, diff_hash: str, generated_at: str, source_locator: str, content_hash: str, verification_method: str, execution_id: str, attempt_id: str, environment_hash: str, generation: EvidenceGeneration, runtime: RuntimeSourceObservation | None)` with canonical `hash`.
- `EvidenceSubmission(content: bytes, status: ObservationStatus, provenance: ProvenanceEnvelope)`.
- `TrustReference(role: TrustRole, evidence_id: str, issuer_id: str, subject_hash: str, action: str, decision: TrustDecision, issued_at: str, expires_at: str, revoked_at: str | None, payload_hash: str, signed_payload_hash: str, verification_method: str, external_verification_receipt: bytes, external_verification_receipt_hash: str)`.
- `TrustedIngestionContext(contract: AcceptanceContract, change_set: ChangeSet, plan: VerificationPlan, repository_id: str, source_tree: str, target_tree: str, observed_at: str, profile: IngestionProfile, expected_profile_hash: str, requirements: tuple[EvidenceRequirement, ...], required_action: str, prerequisite_payload_hashes: tuple[tuple[TrustRole, str], ...])`.
- `IngestionReceipt(context_hash: str, profile_hash: str, bundle_hash: str | None, raw_content_hashes: tuple[str, ...], provenance_hashes: tuple[str, ...], observations: tuple[Observation, ...], freshness: tuple[tuple[str, FreshnessStatus], ...], machine_verified_artifact_ids: tuple[str, ...], human_open_artifact_ids: tuple[str, ...], human_open_reasons: tuple[tuple[str, str], ...], missing_verifier_ids: tuple[str, ...], reason_codes: tuple[str, ...], receipt_hash: str)`; `machine_verified_count` and `human_open_count` are derived properties.
- `IngestionResult(bundle: EvidenceBundle | None, receipt: IngestionReceipt, condition: IntegrityStatus, reason_codes: tuple[str, ...])`.
- `derive_runtime_freshness(observation, evaluation_at)`, `condition_for_ingestion_reasons(reason_codes)`, and `ingest_evidence(context, submissions)`.

Constructors enforce exact types, normalized nonblank timestamp strings, duplicate-free sorted canonical inputs, and bounded lengths. `derive_runtime_freshness` performs RFC3339 UTC parsing so malformed/non-UTC timestamp strings deterministically yield `CONVERGENCE_UNKNOWN`; a physically missing constructor field still raises `TypeError`. Other raw input shape errors raise `TypeError`/`ValueError`; trust/admission failures return an `IngestionResult` with no bundle. Successful admission requires `bundle is not None`, `condition is IntegrityStatus.VALID`, and `reason_codes == ()`; `VALID` without a bundle is forbidden. Every non-VALID result has `bundle=None`.

Failure reasons are unique/sorted and use only this closed vocabulary: `TAMPERED:content_hash`, `TAMPERED:provenance_hash`, `STALE:subject`, `STALE:generation`, `STALE:observation`, `CROSS_BOUND:producer`, `CROSS_BOUND:repository`, `CROSS_BOUND:tree`, `CROSS_BOUND:changeset`, `CROSS_BOUND:artifact`, `CROSS_BOUND:runtime`, `DUPLICATE:artifact`, `DUPLICATE:verifier`, `MALFORMED:profile`, `MALFORMED:requirement`, `MALFORMED:submission`, `MALFORMED:provenance`, `MALFORMED:evidence_type`, `MALFORMED:producer_role`, `MALFORMED:generation`, `MALFORMED:timestamp`, `MALFORMED:runtime`, `MALFORMED:trust_reference`, `MISSING:required_verifier`, `MISSING:source_locator`, `MISSING:execution`, `MISSING:runtime_identity`, `MISSING:ready_identity`, and `MISSING:prerequisite`. Missing verifier IDs are recorded in a separate sorted receipt field and never interpolated into reason strings. Condition precedence is `TAMPERED > STALE > CROSS_BOUND > DUPLICATE > MALFORMED > MISSING`.

`Observation.artifact_hash` is always the canonical provenance-envelope hash. The envelope contains the independently recomputed raw `content_hash`; the ingestion receipt exposes both. Tests independently mutate raw bytes, claimed content hash, and every envelope field.

`EvidenceRequirement` is the independent expected identity for artifact, producer, execution, attempt, environment, raw content, and the complete provenance envelope. Raw bytes must hash to both the requirement's `content_hash` and the envelope's `content_hash`; the computed envelope hash must equal the requirement's `provenance_hash`. Therefore changing raw bytes together with the caller's claimed hash, or changing any envelope field, still fails closed. No submission field may mutate silently or self-update its trust root.

`condition_for_ingestion_reasons` accepts only the closed reason vocabulary and returns the highest-precedence condition, enabling direct pairwise/full precedence tests. Unknown reason codes raise `ValueError`.

### Freshness truth table

All comparisons use caller-supplied, exact RFC3339 UTC `evaluation_at`; no wall clock is read inside Product code. Precedence:

0. A runtime observation carrying `EXECUTION` or `LEGACY_NARRATIVE` generation is invalid at construction and never reaches classification.
1. Missing/malformed fields or non-UTC timestamps → `CONVERGENCE_UNKNOWN`.
2. Observation time after evaluation time, evaluation after `expires_at`, or `observed_generation != desired_generation` → `STALE_OBSERVATION`.
3. Missing desired/loaded source → `CONVERGENCE_UNKNOWN`.
4. `loaded_source_revision != desired_source_revision` → `SOURCE_AHEAD_OF_RUNTIME`.
5. `generation == SOURCE` requires both runtime identities and readiness to be `None`; exact source/generation/time binding then yields `SOURCE_ALIGNED`.
6. `generation == RUNTIME` requires nonblank expected/observed runtime identities and readiness; missing values → `CONVERGENCE_UNKNOWN`.
7. For runtime generation, `observed_runtime_identity != expected_runtime_identity` → `RUNTIME_IDENTITY_MISMATCH`.
8. Runtime evidence whose readiness status is not exact `READY` → `CONVERGENCE_UNKNOWN`.
9. Exact source/runtime identities, exact generation, unexpired observation, and `READY` → `READY_IDENTITY_BOUND`.

Process presence/liveness is not an input capable of producing `READY_IDENTITY_BOUND`.

Admission maps freshness deterministically: malformed/non-UTC time → `MALFORMED`/`MALFORMED:timestamp`; generation mismatch → `STALE`/`STALE:generation`; future/expired observation time → `STALE`/`STALE:observation`; `SOURCE_AHEAD_OF_RUNTIME` → `STALE`/`STALE:subject`; `RUNTIME_IDENTITY_MISMATCH` → `CROSS_BOUND`/`CROSS_BOUND:runtime`; missing desired/loaded source → `MISSING`/`MISSING:source_locator`; missing runtime identity → `MISSING`/`MISSING:runtime_identity`; absent or non-`READY` readiness → `MISSING`/`MISSING:ready_identity`. `SOURCE_ALIGNED` is accepted only for a `SOURCE` requirement that does not require runtime readiness. `READY_IDENTITY_BOUND` is accepted only for a `RUNTIME` requirement. If multiple freshness failures are physically observable, the global condition precedence above applies and all reason codes remain sorted.

### Prerequisite trust boundary

Product does not manage keys or claim to cryptographically verify signatures. It recomputes the hash of the pre-materialized external verification-receipt bytes and validates that receipt identity against a separately supplied, independently expected `IngestionProfile.hash`. A `TrustReference` cannot authorize its own issuer, role, action, or verification method. Receipt bytes and `external_verification_receipt_hash` are mandatory; consumers remain responsible for binding the expected profile hash and upstream cryptographic verifier. `signed_payload_hash` must equal the exact independently expected role payload hash, so a valid signature for another payload fails H6. No `CERTIFIED` result is claimable through the trusted adapter when profile identity, external verification receipt, or any required role is absent/invalid.

`ValidatedPrerequisites` is `init=False`, created only by `validate_prerequisites`, and tracked by an internal weak registry; `certify_ingested` rejects directly constructed/forged values. This is an in-process sealed value, not a durable authority source.

### Exact corpus comparator

The campaign creates `/private/tmp/nexus-product-kernel-usability.LR9utT/run_usability_comparison.py` and runs:

```bash
PYTHONPATH=<candidate-root> python /private/tmp/nexus-product-kernel-usability.LR9utT/run_usability_comparison.py \
  --baseline-manifest /private/tmp/nexus-product-kernel-usability.LR9utT/baseline-manifest.json \
  --baseline-result /private/tmp/nexus-product-kernel-usability.LR9utT/baseline/legacy-nexus-real-world-validation.json \
  --baseline-ledger /private/tmp/nexus-product-kernel-usability.LR9utT/baseline/legacy-nexus-real-world-case-ledger.json \
  --input /private/tmp/nexus-product-kernel-usability.LR9utT/baseline/evaluator-input-v2.json \
  --ground-truth /private/tmp/nexus-product-kernel-usability.LR9utT/baseline/ground-truth-sealed-v2.json \
  --output /private/tmp/nexus-product-kernel-usability.LR9utT/product-kernel-usability-before-after.json
```

The comparator first verifies every manifest file hash, then requires identical 20 case IDs, truth labels, cutoffs, primary/correlation flags, `verification_result`, `certification_disposition`, `evidence_integrity`, false-certification denominators, and high-risk denominators. It fails closed on any difference before calculating usability fields. Quantitative gate: at least 8/20 artifacts machine verified, at most 12/20 human opens, manual followups ≤234, and all safety/replay/binding metrics unchanged.

## Chunk 1: Contracts and TDD

### Task 1: Governance and immutable baseline

**Files:**
- Create: `tasks/product-kernel-usability-repair-20260829/INDEX.md`
- Create: `tasks/product-kernel-usability-repair-20260829/00-product-kernel-usability-repair.md`
- Create: `docs/superpowers/plans/2026-08-29-product-kernel-usability-repair.md`

- [ ] Verify the Owner handoff, base commit/tree, baseline-manifest and seven copied artifact hashes.
- [ ] Independently review this plan for scope, safety invariants, TDD order, and absence of a second authority.
- [ ] Commit the approved governance/plan files before implementation.

### Task 2: Write ingestion and freshness RED tests

**Files:**
- Create: `tests/product/test_trusted_evidence_ingestion.py`
- Test target: `product/evidence/ingestion.py`

- [ ] Write wished-for API tests for `ProvenanceEnvelope`, `EvidenceSubmission`, `IngestionProfile`, `EvidenceRequirement`, `TrustedIngestionContext`, `RuntimeSourceObservation`, `IngestionReceipt`, `IngestionResult`, `derive_runtime_freshness`, and `ingest_evidence`.
- [ ] Add positive tests proving exact artifact bytes, producer/execution/environment identity, repository/revision/tree/change/diff binding, deterministic normalization, and machine-verified versus human-open accounting.
- [ ] Add H1 artifact substitution, H2 stale subject, H3 producer spoofing, H7 stale runtime observation, H9 missing-field/default, H11 type/canonical ambiguity, and H12 duplicate/conflicting provenance tests.
- [ ] Run `python -m pytest -q tests/product/test_trusted_evidence_ingestion.py` and record the expected import/feature-missing RED failure.
- [ ] Commit RED tests only after confirming they fail for the missing trusted-ingestion API.

### Task 3: Implement the minimum ingestion seam

**Files:**
- Create: `product/evidence/ingestion.py`
- Modify: `product/protocol/__init__.py`
- Test: `tests/product/test_trusted_evidence_ingestion.py`

- [ ] Add experimental provenance/ingestion schema constants without changing Public Protocol version or existing evidence/receipt schemas.
- [ ] Implement exact-type frozen enums/dataclasses and canonical hashes.
- [ ] Recompute raw content SHA-256; validate trust-profile producer role/method, execution/environment, exact subject, required evidence generation, and freshness.
- [ ] Derive `SOURCE_ALIGNED`, `SOURCE_AHEAD_OF_RUNTIME`, `RUNTIME_IDENTITY_MISMATCH`, `STALE_OBSERVATION`, `READY_IDENTITY_BOUND`, and `CONVERGENCE_UNKNOWN` from bound fields; never accept caller-declared freshness.
- [ ] On any malformed/tampered/stale/missing/duplicate input, return no trusted bundle with deterministic condition/reasons.
- [ ] On success, create only existing typed `Observation` values and an existing `EvidenceBundle`, with observation hashes bound to provenance-envelope hashes.
- [ ] Run the focused test until GREEN; refactor only after GREEN.

## Chunk 2: Prerequisites and Legacy portability

### Task 4: Write trusted certification and Legacy RED tests

**Files:**
- Create: `tests/product/test_trusted_certification_adapter.py`
- Create: `tests/product/test_legacy_evidence_adapter.py`
- Test targets: `product/adapters/trusted.py`, `product/adapters/legacy.py`

- [ ] Define tests for provenance-capable policy/authority/approval/signing references bound to exact issuer, repository/change-set subject, action, validity, revocation, payload hash, and signed-payload hash.
- [ ] Add H4 authority widening, H5 approval substitution, H6 signing substitution, H8 narrative PASS escalation, and H10 downgrade/fallback tests.
- [ ] Prove missing prerequisite remains BLOCKED, valid policy denial remains REJECTED, and valid complete prerequisites may reach the unchanged core CERTIFIED result.
- [ ] Prove the adapter envelope transitively binds ingestion, prerequisite-profile and core receipt hashes but cannot create a disposition or merge authority.
- [ ] Prove structured Legacy evidence may become a submission only when complete provenance is present; narrative PASS and narrative FAIL remain `LEGACY_NON_CERTIFIABLE`.
- [ ] Run both test files and record expected RED failures before production adapter code exists.

### Task 5: Implement trusted and Legacy adapters

**Files:**
- Create: `product/adapters/trusted.py`
- Create: `product/adapters/legacy.py`
- Test: `tests/product/test_trusted_certification_adapter.py`
- Test: `tests/product/test_legacy_evidence_adapter.py`

- [ ] Validate trust references against the separately supplied issuer/action profile; no reference may self-authorize.
- [ ] Return an internal validated-prerequisite value whose constructor cannot be used as a caller trust root.
- [ ] Derive existing `CertificationInput` booleans only from the validated prerequisite value and call existing `product.kernel.certify`.
- [ ] Return a trusted evidence envelope containing the existing core result/receipt and provenance hashes; do not implement another reducer or receipt authority.
- [ ] Implement Legacy structured-record translation and narrative fail-closed behavior.
- [ ] Run focused tests until GREEN; refactor only after GREEN.

## Chunk 3: Hostile, architecture and real-corpus evidence

### Task 6: Complete H1-H12 and architecture controls

**Files:**
- Modify: `tests/product/test_trusted_evidence_ingestion.py`
- Modify: `tests/product/test_trusted_certification_adapter.py`
- Modify: `tests/product/test_legacy_evidence_adapter.py`
- Modify: `tests/product/test_kernel.py`
- Modify: `docs/testing/test_impact_map.md`

- [ ] Confirm all H1-H12 attacks produce no trusted bundle/prerequisite or retain BLOCKED/REJECTED core truth.
- [ ] Add mutation controls for every hashed producer/execution/tree/trust field and duplicate role/evidence conflicts.
- [ ] Add AST architecture controls: ingestion imports no verifier/certifier/provider/network/filesystem/subprocess surface; adapters call only the existing kernel; existing verification/certification files are unchanged.
- [ ] Map new Product paths to exact new tests in the impact map.
- [ ] Run the three new files, all Product tests, and legacy compatibility tests.

### Task 7: Exact 20-case BEFORE/AFTER and fresh controls

**External artifacts only:** `/private/tmp/nexus-product-kernel-usability.LR9utT/`

- [ ] Keep baseline artifacts read-only and verify their hashes before every comparison.
- [ ] Produce `product-kernel-usability-root-causes.json` with outcome-genuine versus usability-only distinctions.
- [ ] Reuse the exact opaque C001–C020 identities, cutoffs, ground truth, and denominators.
- [ ] Record per case: available artifacts, machine-verified artifacts, human-open artifacts, reason for any remaining human open, ingestion/prerequisite result, and unchanged core outcome.
- [ ] Compare false certification, high-risk false certification, UNVERIFIABLE, replay nondeterminism, binding failure, manual checks/followups, artifact opens, and known-good portability.
- [ ] Only after exact comparison, add 3–5 recent read-only controls that were not used to shape the implementation.
- [ ] Do not reinterpret missing historical evidence or stale subjects as current truth.

## Chunk 4: Acceptance-quality Candidate

### Task 8: Full verification and independent reviews

**Files:** all allowed paths only.

- [ ] Run focused and full relevant tests, Ruff check/format, Product Pyright, compile/import, offline wheel/sdist, and `git diff --check`.
- [ ] Audit exact changed/deleted paths, modes, source imports, no hidden fallback, and no current-case hardcodes.
- [ ] Run exact-base differential for any unrelated broader failure and label baseline debt honestly.
- [ ] Dispatch independent spec-compliance review, then code-quality review, then hostile/security and metric-denominator falsification.
- [ ] Fix every blocking finding and rerun the exact reviewer subject.
- [ ] Commit the verified scoped Candidate and bind exact commit/tree/diff/test identities.

### Task 9: Final usability receipt and terminal

**External artifacts only:** `/private/tmp/nexus-product-kernel-usability.LR9utT/`

- [ ] Create `product-kernel-usability-repair-validation.json`.
- [ ] Create `product-kernel-usability-before-after.json`.
- [ ] Create the final reproducibility receipt with baseline/Candidate/corpus/harness/test/reviewer/environment hashes.
- [ ] State trust boundaries for ingestion, provenance, factual verification, certification recommendation, acceptance evidence and merge-gate evidence.
- [ ] Select `VALUE_SIGNAL_STRONG`, `VALUE_SIGNAL_MIXED`, or `VALUE_SIGNAL_NEGATIVE` from physical evidence.
- [ ] Name exactly one next gate and keep `AUTO_CHAIN=false`.
