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
- `IngestionReceipt(context_hash: str, profile_hash: str, bundle_hash: str | None, raw_content_hashes: tuple[str, ...], provenance_hashes: tuple[str, ...], observations: tuple[Observation, ...], freshness: tuple[tuple[str, FreshnessStatus], ...], machine_verified_artifact_ids: tuple[str, ...], human_open_artifact_ids: tuple[str, ...], human_open_reasons: tuple[tuple[str, str], ...], missing_verifier_ids: tuple[str, ...], reason_codes: tuple[str, ...], receipt_hash: str)`; `machine_verified_count` and `human_open_count` are derived properties. The only initial human-open reason is exact `semantic_review_required`, paired with the bound artifact ID.
- `IngestionResult(bundle: EvidenceBundle | None, receipt: IngestionReceipt, condition: IntegrityStatus, reason_codes: tuple[str, ...])`.
- `IngestionTrustStatus(str, Enum)`: exactly `UNTRUSTED`, `RECEIPT_INVALID`, `TRUSTED`.
- `classify_ingestion_result(context: TrustedIngestionContext, result: IngestionResult) -> IngestionTrustStatus` and `is_trusted_ingestion_result(context: TrustedIngestionContext, result: IngestionResult) -> bool`; the boolean helper is true if and only if classification is `TRUSTED`.
- `derive_runtime_freshness(observation, evaluation_at)`, `condition_for_ingestion_reasons(reason_codes)`, and `ingest_evidence(context, submissions)`.

Constructors enforce exact types, normalized nonblank timestamp strings, duplicate-free sorted canonical inputs, and these exact Task-3 length bounds: `MAX_TEXT_LENGTH=4096`, `MAX_COLLECTION_ITEMS=256`, and `MAX_CONTENT_BYTES=1_048_576` (1 MiB). `derive_runtime_freshness` performs RFC3339 UTC parsing so malformed/non-UTC timestamp strings deterministically yield `CONVERGENCE_UNKNOWN`; a physically missing constructor field still raises `TypeError`. Other raw input shape errors raise `TypeError`/`ValueError`; trust/admission failures return an `IngestionResult` with no bundle. Successful admission requires `bundle is not None`, `condition is IntegrityStatus.VALID`, and `reason_codes == ()`; `VALID` without a bundle is forbidden. Every non-VALID result has `bundle=None`.

Before inspecting submissions, Task 3 requires exact `context.plan.acceptance_contract_hash == context.contract.hash` and `context.plan.change_set_hash == context.change_set.hash`; it does not synthesize a plan or call a requirement-compatibility helper. `context.requirements` must independently contain unique `verifier_id` values and unique `artifact_id` values before any submission is inspected. Each provenance source/target revision and `source_locator` is revalidated at admission as exact built-in `str`, normalized, nonblank, and within `MAX_TEXT_LENGTH`; a `str` subclass in any of these fields is exact `MALFORMED:provenance`, not accepted through string compatibility.

Failure reasons are unique/sorted and use only this closed vocabulary: `TAMPERED:content_hash`, `TAMPERED:provenance_hash`, `STALE:subject`, `STALE:generation`, `STALE:observation`, `CROSS_BOUND:producer`, `CROSS_BOUND:repository`, `CROSS_BOUND:tree`, `CROSS_BOUND:changeset`, `CROSS_BOUND:artifact`, `CROSS_BOUND:execution`, `CROSS_BOUND:runtime`, `DUPLICATE:artifact`, `DUPLICATE:verifier`, `MALFORMED:profile`, `MALFORMED:requirement`, `MALFORMED:submission`, `MALFORMED:provenance`, `MALFORMED:evidence_type`, `MALFORMED:producer_role`, `MALFORMED:generation`, `MALFORMED:timestamp`, `MALFORMED:runtime`, `MALFORMED:trust_reference`, `MISSING:required_verifier`, `MISSING:source_locator`, `MISSING:execution`, `MISSING:runtime_identity`, `MISSING:ready_identity`, and `MISSING:prerequisite`. Missing verifier IDs are recorded in a separate sorted receipt field and never interpolated into reason strings. Condition precedence is `TAMPERED > STALE > CROSS_BOUND > DUPLICATE > MALFORMED > MISSING`.

`Observation.artifact_hash` is always the canonical provenance-envelope hash. The envelope contains the independently recomputed raw `content_hash`; the ingestion receipt exposes both. Tests independently mutate raw bytes, claimed content hash, and every envelope field.

`EvidenceRequirement` is the independent expected identity for artifact, producer, execution, attempt, environment, raw content, and the complete provenance envelope. Raw bytes must hash to both the requirement's `content_hash` and the envelope's `content_hash`; the computed envelope hash must equal the requirement's `provenance_hash`. Therefore changing raw bytes together with the caller's claimed hash, or changing any envelope field, still fails closed. No submission field may mutate silently or self-update its trust root.

`condition_for_ingestion_reasons` accepts only the closed reason vocabulary and returns the highest-precedence condition, enabling direct pairwise/full precedence tests. Unknown reason codes raise `ValueError`.

### Freshness truth table

The shared Task-3 RFC3339 UTC parser accepts the standard `T` date/time separator with either terminal `Z` or `+00:00`, including dot fractional seconds. It rejects a space separator, `+00:00:00`, comma fractional seconds, every non-UTC offset, and all other non-RFC3339 variants. Task 4 must reuse this exact parser behavior.

All comparisons use caller-supplied, exact RFC3339 UTC `evaluation_at`; no wall clock is read inside Product code. Precedence:

0. A runtime observation carrying `EXECUTION` or `LEGACY_NARRATIVE` generation is invalid at construction and never reaches classification.
1. Missing/malformed fields or non-UTC timestamps → `CONVERGENCE_UNKNOWN`.
2. Observation time after evaluation time, evaluation after `expires_at`, or `observed_generation != desired_generation` → `STALE_OBSERVATION`; timestamp/generation staleness is evaluated before missing source identity.
3. Missing desired/loaded source → `CONVERGENCE_UNKNOWN`.
4. `loaded_source_revision != desired_source_revision` → `SOURCE_AHEAD_OF_RUNTIME`.
5. `generation == SOURCE` requires both runtime identities and readiness to be `None`; any non-`None` identity/readiness field is admission-level `MALFORMED:runtime` with no bundle. Exact source/generation/time binding then yields `SOURCE_ALIGNED`.
6. `generation == RUNTIME` always requires a `RuntimeSourceObservation`, regardless of `runtime_ready_required`. A missing runtime observation yields both exact `MISSING:ready_identity` and `MISSING:runtime_identity`; nonblank expected/observed runtime identities and readiness are otherwise required, with missing values → `CONVERGENCE_UNKNOWN`.
7. For runtime generation, `observed_runtime_identity != expected_runtime_identity` → `RUNTIME_IDENTITY_MISMATCH`.
8. Runtime evidence whose readiness status is not exact `READY` → `CONVERGENCE_UNKNOWN`.
9. Exact source/runtime identities, exact generation, unexpired observation, and `READY` → `READY_IDENTITY_BOUND`.

Process presence/liveness is not an input capable of producing `READY_IDENTITY_BOUND`.

Admission maps freshness deterministically: malformed/non-UTC time → `MALFORMED`/`MALFORMED:timestamp`; generation mismatch → `STALE`/`STALE:generation`; future/expired observation time → `STALE`/`STALE:observation`; `SOURCE_AHEAD_OF_RUNTIME` → `STALE`/`STALE:subject`; `RUNTIME_IDENTITY_MISMATCH` → `CROSS_BOUND`/`CROSS_BOUND:runtime`; missing desired/loaded source → `MISSING`/`MISSING:source_locator`; missing runtime identity → `MISSING`/`MISSING:runtime_identity`; absent or non-`READY` readiness → `MISSING`/`MISSING:ready_identity`. Timestamp/generation stale reasons are retained together with any independently observable missing-source reasons rather than short-circuiting them away. `SOURCE_ALIGNED` is accepted only for a `SOURCE` requirement that does not require runtime readiness. `READY_IDENTITY_BOUND` is accepted only for a `RUNTIME` requirement. If multiple freshness failures are physically observable, the global condition precedence above applies and all reason codes remain sorted.

### Prerequisite trust boundary

Task 4 is a consumer of the Task-3 authority seam, not a second authority. It must reuse the exact existing `TrustRole`, `TrustDecision`, `IssuerGrant`, `TrustReference`, `TrustedIngestionContext`, `EvidenceSubmission`, `IngestionResult`, `ingest_evidence`, RFC3339 parser, ingestion-receipt validator, and core `certify`. It must not define another role, decision, issuer, reference, context, clock, verifier, Legacy observation path, reducer, or receipt authority.

Before Task 4 RED tests are claimable, Task 3 must define `IngestionReceipt` and `IngestionResult` as exact `@dataclass(frozen=True, init=False, eq=False)` weak-referenceable values whose public constructors raise, create them only through internal factories, and register minted results by weak identity. The registry is a `WeakKeyDictionary` keyed by the exact result object; its immutable fingerprint value stores an immutable `mint_successful` flag, recomputation material, and a weak reference to the exact context, never a strong context/result dependency, `id()` integer, or dead-entry list. Classification requires `stored_context() is context`; a same-hash/equal-field context clone is `UNTRUSTED`, and garbage collection of the result removes its weak-key entry.

The exact public classifier above owns both diagnostic stages without exposing or duplicating the registry. `UNTRUSTED` means wrong exact type, lookalike, wrong context identity, absent weak-registry identity, not minted for that exact context, or `mint_successful is False`; an originally non-successful admission remains `UNTRUSTED` even if hostile mutation makes its current fields appear successful. `RECEIPT_INVALID` requires `mint_successful is True`, recognized exact minted identity/context, and a later mismatch under full current receipt/result recomputation. `TRUSTED` requires `mint_successful is True`, exact successful identity, and full recomputation pass. Full recomputation requires `condition is IntegrityStatus.VALID`, empty reasons, non-`None` exact bundle, exact context/profile/bundle bindings, and recomputed receipt hash. Task 4 maps only this Task-3 classifier to `UNTRUSTED_INGESTION` versus `INGESTION_RECEIPT_INVALID`; it never reconstructs, accepts a lookalike, or creates its own ingestion registry or authority.

#### Exact source-aligned trusted-adapter API

- `ExternalReceiptExpectation`, frozen `@dataclass(init=False, eq=False)` and weak-referenceable, has exactly these fields in order: `context_hash`, `subject_hash`, `profile_hash`, `role`, `evidence_id`, `issuer_id`, `expected_payload_hash`, `required_action`, `verification_method`, `external_verification_receipt_hash`. It has a computed `hash`; public construction always raises and copied/lookalike values are invalid.
- Its hash is the canonical repository hash of exactly `("nexus.external_receipt_expectation.v1-experimental", context_hash, subject_hash, profile_hash, role.value, evidence_id, issuer_id, expected_payload_hash, required_action, verification_method, external_verification_receipt_hash)`.
- The only mint path is exact module-private `_bootstrap_external_receipt_expectation(*, context: TrustedIngestionContext, ingestion: IngestionResult, role: TrustRole, expected_evidence_id: str, expected_issuer_id: str, expected_verification_method: str, independently_expected_receipt: bytes) -> ExternalReceiptExpectation`. It accepts neither a raw expected hash nor a `TrustReference`. It first requires `is_trusted_ingestion_result(context, ingestion)`, exact profile equality, exact role payload root, and an `IssuerGrant` authorizing the expected issuer/role, `context.required_action`, and `expected_verification_method`. It then derives `context_hash`, prerequisite `subject_hash`, `profile_hash`, `expected_payload_hash`, `required_action`, and the physical receipt SHA-256 internally. `evidence_id`, issuer, and method come only from trusted bootstrap metadata and are never copied from a submitted reference. The factory weak-identity-registers the value and has no fallback.
- `_bootstrap_external_receipt_expectation` is not in `__all__`, is not exported by Legacy, is never called by `validate_prerequisites` or submission parsing, and is never reachable as a fallback. Python module privacy is not a security boundary: deployment must restrict this bootstrap to the trusted composition layer that owns independently expected receipt bytes and evidence metadata.
- `PrerequisiteValidationStatus`: exactly `VALIDATED`, `INVALID`.
- `PrerequisiteValidationResult(status: PrerequisiteValidationStatus, prerequisites: ValidatedPrerequisites | None, reason_codes: tuple[str, ...])` is frozen. Attacker-controlled invalid input returns `INVALID`, `prerequisites=None`, and only the exact decision-table reason tuple below; validation-shape failures are not exceptions.
- `ValidatedPrerequisites`, frozen `@dataclass(init=False, eq=False)` and weak-referenceable, has exactly `subject_hash`, `context_hash`, `profile_hash`, `ingestion_bundle_hash`, `ingestion_receipt_hash`, `observed_at`, `policy_accepted`, `authority_present`, `approval_present`, `signing_present`, `reference_hashes`, `expectation_hashes` in that order and a computed `hash`. Public construction always raises; only successful validation may internally create and weak-identity-register it.
- `validate_prerequisites(context: TrustedIngestionContext, ingestion: IngestionResult, references: tuple[TrustReference, ...], receipt_expectations: tuple[ExternalReceiptExpectation, ...]) -> PrerequisiteValidationResult`.
- `TrustedCertificationResult`, frozen `@dataclass(init=False, eq=False)` and weak-referenceable, has exactly `context_hash: str`, `profile_hash: str`, `ingestion_bundle_hash: str`, `ingestion_receipt_hash: str`, `prerequisite_subject_hash: str`, `prerequisites_hash: str`, `core_receipt_hash: str`, `core_result: CertificationResult` in that order and a computed `hash`. Public construction always raises; only `certify_ingested` may create it.
- `certify_ingested(context: TrustedIngestionContext, ingestion: IngestionResult, prerequisites: ValidatedPrerequisites) -> TrustedCertificationResult`.
- `is_trusted_certification_result(context: TrustedIngestionContext, ingestion: IngestionResult, prerequisites: ValidatedPrerequisites, result: TrustedCertificationResult) -> bool` never raises for attacker input.

The exact prerequisite subject is the canonical hash of:

```text
("nexus.trusted_prerequisite_subject.v1-experimental",
 context.hash,
 ingestion.bundle.hash)
```

The prerequisite hash is the canonical hash of exactly:

```text
("nexus.validated_prerequisites.v1-experimental",
 subject_hash, context_hash, profile_hash,
 ingestion_bundle_hash, ingestion_receipt_hash, observed_at,
 policy_accepted, authority_present, approval_present, signing_present,
 reference_hashes, expectation_hashes)
```

`reference_hashes` and `expectation_hashes` are exact four-item tuples ordered `POLICY`, `AUTHORITY`, `APPROVAL`, `SIGNING`. There must be exactly one existing Task-3 `TrustReference` and one registry-minted expectation for every existing `TrustRole`; missing, duplicate, extra, wrong-type, or wrong-order-normalization input yields `ROLE_SET_INVALID` or `EXPECTATION_SET_INVALID`. V2 adds no cross-role receipt-ID or receipt-byte uniqueness rule beyond the existing Task-3 issuer grants and exact per-role bindings.

The sealed value binds `context_hash=context.hash`, `profile_hash=context.expected_profile_hash`, `ingestion_bundle_hash=ingestion.bundle.hash`, `ingestion_receipt_hash=ingestion.receipt.hash`, and `observed_at=context.observed_at`; its ordered reference/expectation hashes are the corresponding existing reference hashes and registry-minted expectation hashes. The wrapper repeats those physical bindings, uses `prerequisite_subject_hash=prerequisites.subject_hash`, `prerequisites_hash=prerequisites.hash`, and `core_receipt_hash=core_result.receipt.hash`, and rejects any mismatch.

Validation first requires `is_trusted_ingestion_result(context, ingestion)`, exact `context.profile.hash == context.expected_profile_hash`, and exact subject/context/bundle/receipt bindings. For each role it then requires an issuer in `context.profile.issuers` granting that exact role, `context.required_action`, and the reference's verification method; `reference.action` must equal `context.required_action`. `context.prerequisite_payload_hashes` must independently contain exactly one `expected_hash` for every role. It then requires both `reference.payload_hash == expected_hash` and `reference.signed_payload_hash == expected_hash`. H5 mismatch is exact `<ROLE>:PAYLOAD_HASH_MISMATCH`; H6 mismatch is exact `<ROLE>:SIGNED_PAYLOAD_HASH_MISMATCH`. A missing role root is top-level `UNTRUSTED_CONTEXT`, mints no prerequisite, and keeps the core call count at zero.

Claim ceiling: equality of `signed_payload_hash` to the independently context-bound expected hash does **not** prove a cryptographic signature. External trust comes only from the compatible existing `IssuerGrant`, granted `verification_method`, and registry-minted independently pinned external receipt. Product manages no key, performs no cryptography, invents no second signed-payload root, and creates no second authority.

External receipt validation recomputes the physical bytes hash and requires exact equality with both `reference.external_verification_receipt_hash` and the registry-minted expectation hash. It compares every expectation field against the exact context, ingestion subject, context role root/action, reference identity, granted verification method, and physical receipt. The same receipt reused with a different context or bundle therefore fails exact `<ROLE>:EXTERNAL_RECEIPT_EXPECTATION_MISMATCH`. A colluding reference plus caller-created expectation cannot pass because expectation weak-registry identity and all derived fields are required.

Time uses the Task-3 RFC3339 UTC parser and the exact cutoff `context.observed_at`; Task 4 has no `now`, wall-clock read, or `max_age_seconds`. A reference is temporally admissible only when `issued_at <= observed_at` and `observed_at < expires_at`. Equality at issuance is valid; equality at expiry is expired. `revoked_at <= observed_at` is invalid, while revocation after the cutoff does not rewrite the earlier observation. Malformed/non-UTC timestamps return role-scoped timestamp reasons.

Failure selection is an exact two-level first-failure decision table.

- **Level A:** short-circuit at the first applicable reason in exact order `MALFORMED_INPUT`, `UNTRUSTED_CONTEXT`, `PROFILE_MISMATCH`, `UNTRUSTED_INGESTION`, `INGESTION_RECEIPT_INVALID`, `ROLE_SET_INVALID`, `EXPECTATION_SET_INVALID`; perform no role checks. It must consume `classify_ingestion_result(context, ingestion)` directly: `UNTRUSTED -> UNTRUSTED_INGESTION`, `RECEIPT_INVALID -> INGESTION_RECEIPT_INVALID`, and only `TRUSTED` continues. It must not reimplement classification or inspect a second registry.
- **Level B:** evaluate roles in exact tuple order `POLICY`, `AUTHORITY`, `APPROVAL`, `SIGNING`, preserving that order rather than lexical sorting. Emit at most one first reason per role using exact check order `SUBJECT_MISMATCH`, `EXTERNAL_RECEIPT_EXPECTATION_MISMATCH`, `ACTION_MISMATCH`, `ISSUER_GRANT_MISSING`, `ISSUER_GRANT_MISMATCH`, `PAYLOAD_HASH_MISMATCH`, `SIGNED_PAYLOAD_HASH_MISMATCH`, `TIMESTAMP_MALFORMED`, `ISSUED_AFTER_OBSERVED_AT`, `EXPIRED_AT_OBSERVED_AT`, `REVOKED_AT_OBSERVED_AT`, `EXTERNAL_RECEIPT_HASH_MISMATCH`, `EXTERNAL_RECEIPT_EXPECTATION_MISMATCH`. A missing grant means no exact issuer-plus-role grant. A mismatched grant means that grant exists but its action, method, or other constraints fail. Role codes are exact `<ROLE>:<CHECK>`.

No validation result contains `EXTERNAL_RECEIPT_EXPECTATION_MISSING`, `VERIFICATION_METHOD_MISMATCH`, or `SIGNED_PAYLOAD_UNVERIFIABLE`. Level-A output is the one short-circuit reason; Level-B output is the deterministic role-order tuple with at most four unique reasons.

After complete provenance validation, existing semantics map exact `TrustDecision` values: `POLICY/DENY -> policy_accepted=False` and therefore unchanged-core `REJECTED`; `AUTHORITY`, `APPROVAL`, or `SIGNING` DENY maps only its corresponding presence to `False` and therefore unchanged-core `BLOCKED`; ALLOW maps the corresponding value to `True`. Invalid provenance mints no booleans and the core call count remains zero.

`certify_ingested` revalidates the Task-3 trusted-ingestion capability, receipt/profile/registry/subject bindings, then builds the existing `CertificationInput` with `ingestion.bundle` and calls the unchanged core exactly once. Each failed step raises exact `ValueError("invalid_trusted_certification_input:<CODE>")`, where `<CODE>` is one of `UNTRUSTED_CONTEXT`, `UNTRUSTED_INGESTION`, `INGESTION_RECEIPT_INVALID`, `PROFILE_MISMATCH`, `UNTRUSTED_PREREQUISITES`, `SUBJECT_MISMATCH`. It never repairs or downgrades invalid input.

Trusted results use a module-private `WeakKeyDictionary[result, binding]`. Each binding stores only weak references to the exact context, ingestion, and prerequisites plus the minted wrapper hash; it stores no `id()` integer and no strong dependency reference. `is_trusted_certification_result` requires exact dependency identity and liveness, Task-3 trust plus full ingestion receipt/result recomputation, registered prerequisite identity plus full subject/field/hash recomputation, and exact wrapper fields/hash plus registry-minted hash. It rebuilds the exact `CertificationInput`, independently calls unchanged core `certify` exactly once, and compares receipt, verification, and disposition with `result.core_result`. A clone, stale identity, dependency substitution, core substitution, mutated field, collected dependency, or registry mismatch returns `False` without exception. Initial `certify_ingested` creation performs one core call; each later validator invocation separately performs one core call.

The trusted wrapper hash is the canonical hash of exactly:

```text
("nexus.trusted_certification_wrapper.v1-experimental",
 context_hash, profile_hash, ingestion_bundle_hash,
 ingestion_receipt_hash, prerequisite_subject_hash,
 prerequisites_hash, core_receipt_hash)
```

The wrapper does not duplicate disposition/verification fields in its hash; they are already transitively sealed by `core_receipt_hash` and `core_result` must physically match that receipt.

#### Exact source-aligned Legacy adapter

There is no Legacy schema, record ID, wire loader, or serialized reconstruction surface. `LegacyAdapterResult` is frozen with exactly `ingestion: IngestionResult | None`, `fallback_integrity: IntegrityStatus | None`, and `reasons: tuple[str, ...]`. `adapt_legacy_evidence(context: TrustedIngestionContext, value: object) -> LegacyAdapterResult` behaves exactly:

- structured input is accepted only when `type(value) is EvidenceSubmission`; it calls existing `ingest_evidence(context, (value,))` exactly once and returns `LegacyAdapterResult(ingestion=result, fallback_integrity=None, reasons=())` without interpreting PASS/FAIL;
- a dictionary, faux wire payload, or malformed structured lookalike returns `LegacyAdapterResult(None, IntegrityStatus.MALFORMED, ("LEGACY_STRUCTURED_MALFORMED",))`;
- narrative strings, legacy caller reasons, or narrative PASS/FAIL return `LegacyAdapterResult(None, IntegrityStatus.LEGACY_NON_CERTIFIABLE, ("LEGACY_NARRATIVE_NON_CERTIFIABLE",))`.

The Legacy adapter never creates a direct `Observation`, `EvidenceBundle`, ingestion receipt/result, prerequisite, or certification result. All structured authority flows through Task-3 `ingest_evidence` and its sealed result.

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
- [ ] Add Task-3 diagnostic RED controls proving exact `IngestionTrustStatus`, public classifier signature, `is_trusted_ingestion_result` iff `TRUSTED`, wrong-type/lookalike/unregistered/same-hash-context-clone `UNTRUSTED`, honestly minted non-VALID/reasoned/bundle-less admission `UNTRUSTED`, recognized-minted successful post-mutation `RECEIPT_INVALID`, valid full recomputation `TRUSTED`, exact-context weakref identity, immutable fingerprint, weak-key GC removal, no strong/dead/id storage, and no second diagnostic registry.
- [ ] Add `mint_successful` RED controls proving an originally non-successful mint remains `UNTRUSTED` after fields are mutated to look successful, while an originally successful mint later mismatching its fingerprint/full recomputation becomes `RECEIPT_INVALID`.
- [ ] Add exact shared RFC3339 parser RED controls: accept `T` plus `Z`/`+00:00` and dot fractions; reject space separator, `+00:00:00`, comma fractions, and non-UTC offsets.
- [ ] Add stable-combination RED controls for exact plan contract/change equality without a compatibility helper, independently duplicate requirement verifier/artifact IDs, exact bounded source revisions/locator including `str` subclass rejection, stale-plus-missing-source reason retention, SOURCE non-`None` runtime identity/readiness malformed behavior, and RUNTIME-without-observation dual missing reasons even when runtime readiness is not requested.
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
- [ ] Require exact plan contract/change hashes and independently unique requirement verifier/artifact IDs before submissions; revalidate exact normalized bounded source revisions and locator at admission without synthesized compatibility.
- [ ] Derive `SOURCE_ALIGNED`, `SOURCE_AHEAD_OF_RUNTIME`, `RUNTIME_IDENTITY_MISMATCH`, `STALE_OBSERVATION`, `READY_IDENTITY_BOUND`, and `CONVERGENCE_UNKNOWN` from bound fields; never accept caller-declared freshness.
- [ ] On any malformed/tampered/stale/missing/duplicate input, return no trusted bundle with deterministic condition/reasons.
- [ ] On success, create only existing typed `Observation` values and an existing `EvidenceBundle`, with observation hashes bound to provenance-envelope hashes.
- [ ] Seal `IngestionReceipt` and `IngestionResult` as exact frozen/init-false/eq-false internally minted weak values; implement the exact weak-key/context-weakref immutable fingerprint plus classifier/iff helper boundary, treating minted non-success as `UNTRUSTED` and reserving `RECEIPT_INVALID` for later mutation of a recognized successful result.
- [ ] Enforce exact `MAX_TEXT_LENGTH=4096`, `MAX_COLLECTION_ITEMS=256`, and `MAX_CONTENT_BYTES=1_048_576` limits at the Task-3 boundary.
- [ ] Run the focused test until GREEN; refactor only after GREEN.

## Chunk 2: Prerequisites and Legacy portability

### Task 4: Write trusted certification and Legacy RED tests

**Files:**
- Create: `tests/product/test_trusted_certification_adapter.py`
- Create: `tests/product/test_legacy_evidence_adapter.py`
- Test targets: `product/adapters/trusted.py`, `product/adapters/legacy.py`

- [ ] **T4-1 Task-3 authority reuse:** assert trusted/Legacy modules reuse the exact existing Task-3 role, decision, grant, reference, context, submission, result, RFC3339 parser, `IngestionTrustStatus`, classifier, boolean validator, and ingestion symbols and export no parallel equivalents.
- [ ] **T4-2 four-role cardinality:** exact one reference and registry-minted expectation per `POLICY`, `AUTHORITY`, `APPROVAL`, `SIGNING` validates; missing/duplicate/extra/wrong-type sets return exact set reasons.
- [ ] **T4-3 context roots:** mutate expected profile, context prerequisite roots, context hash, bundle hash, or ingestion receipt binding and prove no prerequisites/core call.
- [ ] **T4-4 H4 issuer grant:** absent issuer or role grant returns exact role-scoped issuer reason and cannot widen authority.
- [ ] **T4-5 H4 action binding:** reference action substitution returns `<ROLE>:ACTION_MISMATCH`.
- [ ] **T4-6 H4 method binding:** a reference or expectation method mismatch is caught by expectation identity; a compatible issuer-role grant that does not grant the expected method returns `<ROLE>:ISSUER_GRANT_MISMATCH`.
- [ ] **T4-7 H5 payload binding:** H5-A mutates only the reference payload hash and returns `<ROLE>:PAYLOAD_HASH_MISMATCH`; the positive control uses exact `context.prerequisite_payload_hashes[role]` and passes this gate.
- [ ] **T4-8 H6 signed-payload binding:** H6-A mutates only the signed-payload hash and returns `<ROLE>:SIGNED_PAYLOAD_HASH_MISMATCH`; the positive control binds both payload hashes to the exact same independent context role root. Missing role root returns top-level `UNTRUSTED_CONTEXT` and core zero.
- [ ] **T4-9 receipt bytes:** mutate raw receipt bytes or either recorded hash and require `<ROLE>:EXTERNAL_RECEIPT_HASH_MISMATCH`.
- [ ] **T4-10 expectation self-authorization A/B/C:** **A** the exact bootstrap accepts context, trusted ingestion, independent receipt bytes, and trusted evidence/issuer/method metadata but no raw expected hash or reference; **B** submitted reference identity/bytes cannot select any derived expectation field; **C** validation, Legacy parsing, public constructors, copying, and fallback paths cannot mint expectations. Add independent-bootstrap positive controls for every derived field plus caller-created/copied negative controls.
- [ ] **T4-11 subject binding:** reference or prerequisite subject substitution fails before core invocation.
- [ ] **T4-12 RFC3339 issuance cutoff:** exact equality at issuance passes; future, malformed, and non-UTC issuance values return exact role-scoped reasons.
- [ ] **T4-13 RFC3339 expiry cutoff:** cutoff strictly before expiry passes; equality/after returns `<ROLE>:EXPIRED_AT_OBSERVED_AT`; malformed/non-UTC fails closed.
- [ ] **T4-14 RFC3339 revocation cutoff:** revocation at/before cutoff returns `<ROLE>:REVOKED_AT_OBSERVED_AT`; a valid future revocation does not rewrite past truth.
- [ ] **T4-15 DENY mappings:** policy DENY produces unchanged-core `REJECTED`; authority/approval/signing DENY independently produce unchanged-core `BLOCKED`; no unrelated boolean changes.
- [ ] **T4-16 invalid core-zero matrix:** every validation failure follows the exact Level-A short-circuit or Level-B role-order decision table, mints no booleans, and calls core zero times.
- [ ] **T4-17 valid core-once matrix:** complete ALLOW and each fully validated DENY case calls the unchanged core exactly once and the wrapper matches its physical result/receipt.
- [ ] **T4-18 forged prerequisites:** public construction, `object.__new__`, replacement/copy, lookalike, mutation, and unregistered/stale capability attacks fail with exact certification input codes.
- [ ] **T4-19 ingestion receipt mutation:** mutate every Task-3 receipt/result field, claimed/computed hash, registry identity, and context/bundle/profile binding; assert honestly minted non-success and same-hash context clones are `UNTRUSTED`, while only a recognized exact-context successful result later failing fingerprint/full recomputation is `RECEIPT_INVALID`.
- [ ] **T4-20 wrapper mutation:** mutate each of the seven wrapper hash fields or mismatch `core_result`/`core_receipt_hash`; hash/revalidation fails without duplicate disposition semantics.
- [ ] **T4-21 Legacy through ingestion only:** only an exact existing `EvidenceSubmission` object calls `ingest_evidence` once; narratives/caller reasons are Legacy non-certifiable, dictionaries/faux-wire/lookalikes are malformed, and neither fallback constructs Product evidence/results.
- [ ] **T4-22 expectation cross-context replay:** an expectation minted for another exact context is rejected with `<ROLE>:EXTERNAL_RECEIPT_EXPECTATION_MISMATCH` even when receipt bytes and reference otherwise agree.
- [ ] **T4-23 expectation cross-bundle replay:** changing only the trusted ingestion bundle/subject rejects a previously minted expectation with the same exact role reason.
- [ ] **T4-24 expectation payload/action/method replay:** mutate each internally derived payload root, required action, or verification method and prove all expectation fields are compared before reference authority can pass.
- [ ] **T4-25 bootstrap derived-field controls:** assert the exact private signature, absence of raw-hash/reference inputs, successful internal derivation of every field, compatible grant requirement, weak registry mint, private export boundary, and no validation/Legacy fallback call path.
- [ ] **T4-26 Legacy exact-object/dict boundary:** exact-type `EvidenceSubmission` calls ingestion once; the identical-looking dictionary/faux wire is exact malformed and never reconstructed.
- [ ] **T4-27 top-level short-circuit:** parameterize every Level-A reason and combinations; assert exactly the earliest reason and zero role checks/core calls.
- [ ] **T4-28 ingestion reason boundary:** consume the public classifier directly; wrong/unregistered/cross-context/same-hash-context-clone and minted non-success results classify `UNTRUSTED` and yield `UNTRUSTED_INGESTION`; only a recognized exact-context minted successful result later failing full recomputation classifies `RECEIPT_INVALID` and yields `INGESTION_RECEIPT_INVALID`; only `TRUSTED` advances.
- [ ] **T4-29 issuer missing/mismatch:** no exact issuer-role grant yields `ISSUER_GRANT_MISSING`; an existing grant that fails action/method/constraints yields `ISSUER_GRANT_MISMATCH` at its exact decision-table position.
- [ ] **T4-30 deterministic role aggregation:** multiple role failures emit at most one reason per role in `POLICY`, `AUTHORITY`, `APPROVAL`, `SIGNING` order, never lexical order.
- [ ] **T4-31 result clone false:** field-identical copied/replaced/lookalike `TrustedCertificationResult` fails the weak identity registry validator without exception.
- [ ] **T4-32 wrong dependency identity:** substitute equal-looking context, ingestion, or prerequisites and require `is_trusted_certification_result` false.
- [ ] **T4-33 stale identity reuse:** collect registered capabilities and allocate new objects; stale `id()` reuse and same-hash context clones cannot validate because registries use exact weak object keys/context references, not integers or value equality.
- [ ] **T4-34 full recomputation tamper matrix:** mutate every ingestion receipt/result, prerequisite subject/field/hash, wrapper field/hash, registry minted hash, and dependency liveness input; validation returns false.
- [ ] **T4-35 core substitution:** monkeypatch or replace core result/receipt/verification/disposition and prove independent exact `CertificationInput` recertification detects it; creation core count one and each validation core count one.
- [ ] **T4-36 weak-registry GC:** prove ingestion/result registry fingerprints and trusted-result bindings retain no strong context/ingestion/prerequisite references or dead lists, collected dependencies invalidate validation, and weak-key entries disappear after result collection.
- [ ] Add architecture falsification controls A–I: **A** no second role/decision/grant/reference/context; **B** exact Task-3 symbol reuse; **C** eq-false weak-registry-only expectation/prerequisite/wrapper minting with no `id()`/strong dependency storage; **D** sealed weak Task-3 ingestion receipt/result capability; **E** no clock or timestamp parser other than Task 3; **F** no crypto/verifier claim; **G** invalid core-zero, creation core-one, and validation core-one; **H** Legacy exact evidence reaches only `ingest_evidence`; **I** no edits/import-cycle into existing kernel, verification, or certification reducers.
- [ ] Run both test files and verify every T4-1 through T4-36 case fails for the intended missing adapter API before production adapter code exists.

### Task 5: Implement trusted and Legacy adapters

**Files:**
- Create: `product/adapters/trusted.py`
- Create: `product/adapters/legacy.py`
- Test: `tests/product/test_trusted_certification_adapter.py`
- Test: `tests/product/test_legacy_evidence_adapter.py`

- [ ] Reuse the exact Task-3 trust/context/ingestion types, classifier, boolean validator, and helpers; implement only the registry-minted `ExternalReceiptExpectation`, exact private bootstrap factory, validation result, sealed prerequisites, sealed wrapper, and adapter functions frozen above.
- [ ] Match exact existing issuer role/action/method grants, independent context payload roots, physical receipt bytes, registry-minted expectation identity, RFC3339 cutoff, and exact subject.
- [ ] Derive existing `CertificationInput` booleans only after complete validation and call unchanged `product.kernel.certify` exactly once; all invalid paths call it zero times.
- [ ] Return the exact sealed wrapper with seven transitive hashes and the physical unchanged core result; do not duplicate reducer outputs or create a second authority.
- [ ] Implement `is_trusted_certification_result` with the exact weak dependency binding and full independent Task-3/prerequisite/core/wrapper recomputation; return only bool for hostile inputs.
- [ ] Implement only the exact Legacy exact-object boundary and route the existing submission through existing `ingest_evidence`; all narratives/dictionaries/lookalikes use bounded fallback and never reconstruct or construct evidence.
- [ ] Do not modify `product/kernel`, `product/verification`, or `product/certification`; any required core-semantic change is outside Task 4/5 and must stop as a new Owner boundary.
- [ ] Run focused tests until GREEN; refactor only after GREEN.

Task-4/5 contract status: `OWNER_DECISION_REQUIRED=none`; `TASK4_V2_2_FINAL_SOURCE_GAPS_FROZEN_FOR_RED`; `AUTO_CHAIN=false`.

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
