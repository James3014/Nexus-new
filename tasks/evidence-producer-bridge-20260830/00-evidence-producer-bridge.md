# Task Card: TASK-EPB-001

Status: `ACTIVE`

Campaign: `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`

Goal: prove that one real prospective Nexus-controlled `CandidateVerifier` execution emits independently bound evidence that the unchanged Product Task3 consumer accepts as trusted.

Source mode: `APPROVED_NON_SPEC`

## Authority and claim ceiling

- Owner explicitly authorized the Primary Controller to create and execute this bounded contract.
- Repository: `James3014/Nexus-new`.
- Bound source Candidate/tree: `58a2af2d86cd92aad1d98b6bc708f9ea564fe226` / `ff7526bb78ae639607673ee7ae9ada944a85082d`.
- Bound preflight receipt file SHA-256: `03f3d1e3943a83c2b0b0785480bbcdbf50e610894554b77dc832fbe74adcd126`.
- Authority includes Task3 producer-side bridge implementation, tests, a scoped commit/Candidate, and independent physical verification.
- Authority excludes Task4 prerequisite/authority/signing, approval, merge, push, PR mutation, release, production, public protocol claims, Cloud/OIDC/RBAC, and commercial activation.
- The implementation worker cannot approve, integrate, merge, or act as its own independent verifier.
- `AUTO_CHAIN=false`; parallel execution is disabled.

## Required contract chain

`pre-execution trusted context -> independently compiled EvidenceRequirement -> real verifier execution -> immutable raw artifact -> controller-derived subject/execution/environment provenance -> EvidenceSubmission -> existing ingest_evidence -> existing is_trusted_ingestion_result == True`

## Requirements

1. `REQ-EPB-001`: controller-owned execution subject binds repository, source revision/tree, target revision/tree, ChangeSet/hash, diff, `execution_id`, and `attempt_id`; worker output is not a trust root.
2. `REQ-EPB-002`: compile and freeze `EvidenceRequirement` before execution from an existing acceptance/verification/verifier contract only. It must not inspect observed output, ground truth, later acceptance, or certification state.
3. `REQ-EPB-003`: derive producer id, role, software hash, and method from Nexus-controlled implementation/configuration identity, not worker self-attestation, and create no new authority registry.
4. `REQ-EPB-004`: derive a deterministic provider-neutral environment fingerprint from Nexus-controlled, non-secret, relevant execution facts; missing required inputs fail closed.
5. `REQ-EPB-005`: store raw evidence in immutable content-addressed storage using physically recomputed SHA-256; read back and rehash; reuse only byte-identical content; reject overwrite conflict; bind the locator; existence alone never means PASS.
6. `REQ-EPB-006`: keep observed verifier result separate from the pre-execution expected requirement; observed PASS cannot manufacture expected PASS.
7. `REQ-EPB-007`: construct the existing `ProvenanceEnvelope` only from controller subject, frozen requirement, Nexus producer identity, physical content hash, execution/attempt, environment, method, timestamp/locator, and only genuinely observed runtime facts.
8. `REQ-EPB-008`: use only existing Task3 consumer types and functions: `EvidenceSubmission`, `TrustedIngestionContext`, `ingest_evidence`, `classify_ingestion_result`, and `is_trusted_ingestion_result`. Do not create a parallel classifier, factory, registry, fallback, trusted receipt, or bundle minter.
9. `REQ-EPB-009`: provide at least one real prospective execution through `CandidateVerifier`; a Product-only fixture is insufficient. A deterministic local verifier is acceptable and must not require an external model.
10. `REQ-EPB-010`: any missing or mismatched binding emits no trusted bundle, accepts no caller substitution, and returns a bounded failure reason.
11. `REQ-EPB-011`: do not construct or validate Task4 `TrustReference`, expectation, prerequisite, policy, authority, approval, signing, or issuer semantics.

## Allowed repository paths

Production paths, maximum `6`:

- `nexus/orchestrator/candidate_verifier.py`
- `nexus/evidence/execution_subject.py`
- `nexus/evidence/environment_fingerprint.py`
- `nexus/evidence/artifact_store.py`
- `nexus/evidence/requirement_compiler.py`
- `nexus/evidence/product_ingestion_bridge.py`

Test and governance paths:

- `tests/nexus/evidence/**`
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/product/test_trusted_evidence_ingestion.py`
- `tasks/evidence-producer-bridge-20260830/INDEX.md`
- `tasks/evidence-producer-bridge-20260830/00-evidence-producer-bridge.md`

Maximum total changed paths: `14`.

## Forbidden scope

- Any production mutation under `product/verification/**`, `product/certification/**`, `product/kernel/**`, `product/evidence/**`, `product/protocol/**`, `product/adapters/trusted.py`, `product/adapters/legacy.py`, or `product/adapters/github.py`.
- `CapabilityPlanner`, Workforce Admission, standing-grant, Goal, approval, issuer, signing, cryptographic trust-root, merge, release, deployment, or production semantics.
- Ground truth, evaluator output, historical outcomes, certification disposition, prior booleans, worker prose, worker-declared repository/revision, caller-supplied trusted hashes, or observed PASS as trusted-input sources.
- Direct construction of trusted `EvidenceBundle`, `IngestionResult`, or receipt; bypass of `ingest_evidence`; any second registry/classifier/fallback; provenance downgrade.
- Optional GitHub adapter mutation is not authorized by this card.

## Mandatory RED gates

Before production implementation, tests must run and fail for the intended missing bridge behavior:

1. no prospective bridge exists;
2. requirement must predate result;
3. artifact substitution fails;
4. subject substitution fails;
5. producer spoof fails;
6. execution/attempt replay fails;
7. environment substitution fails;
8. metadata without raw bytes fails;
9. observed PASS cannot create expected PASS;
10. stale-subject replay fails;
11. CAS overwrite conflict fails;
12. direct trusted-object minting is unavailable.

Import/fixture/setup failure does not count as RED.

## GREEN and verification gates

- One real prospective `CandidateVerifier` execution produces raw bytes and reaches unchanged Task3 ingestion.
- Requirement is physically frozen before observed output.
- Artifact bytes are read back and their SHA-256 is recomputed.
- Subject, producer, execution, attempt, and environment bindings are independently derived and hostile substitution/replay tests fail closed.
- Existing Task3 ingestion succeeds and `is_trusted_ingestion_result(context, result)` returns true for the positive witness.
- Repeat the prospective witness and either prove deterministic bindings or label the exact nondeterministic fields.
- Run focused new evidence tests, narrow `CandidateVerifier` tests, Product Task3 focused plus hostile tests, and an impact-selected regression subset.
- Run Ruff check/format, Pyright for affected scope, compile/import checks, and `git diff --check`.
- Audit exact changed/deleted paths and classify unrelated failures against the exact base.
- Independent reviewer must answer: “Does this Candidate prove that one real prospective Nexus verifier execution can emit independently bound evidence accepted as TRUSTED by the unchanged Task3 consumer, without the bridge becoming a new factual, certification, prerequisite, or authority source?”

## Exit and STOP

- PASS terminal: `EVIDENCE_PRODUCER_BRIDGE_VALIDATED`.
- Any need for a new trust root, product/factual/certification semantics, Task4 prerequisite/authority/signing, scope expansion, or unavailable required capability is a hard stop for Owner/controller adjudication.
- After terminal verification, STOP. No successor task is auto-created or executed.

`AUTO_CHAIN=false`
