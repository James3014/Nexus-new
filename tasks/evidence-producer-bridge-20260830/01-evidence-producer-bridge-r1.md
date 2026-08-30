# Task Card: TASK-EPB-001-R1

task_id: `TASK-EPB-001-R1`

Status: `ACTIVE`

Campaign: `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`

Goal: correct the retained `TASK-EPB-001` attempt and prove that one real prospective Nexus-controlled `CandidateVerifier` execution emits independently bound evidence that the unchanged Product Task3 consumer accepts as trusted.

Source mode: `APPROVED_NON_SPEC`

## Lineage and authority

- Same Owner-authorized `EVIDENCE_PRODUCER_BRIDGE_CONTRACT`; this is a bounded correction, not a new product Gate or auto-chained successor Goal.
- Original factual source Candidate/tree remain `58a2af2d86cd92aad1d98b6bc708f9ea564fe226` / `ff7526bb78ae639607673ee7ae9ada944a85082d`.
- Preflight receipt file SHA-256 remains `03f3d1e3943a83c2b0b0785480bbcdbf50e610894554b77dc832fbe74adcd126`.
- Current accepted controller source is `e9b0ec16f6ef72052a4374f24687f6de86a635ff`; its Planner/Workforce-only delta has no Product or EPB production overlap.
- Supersedes failed lifecycle task `TASK-EPB-001`, attempt `attempt-f8800f9da0fc4150b9f8f0b132347403`, retained target commit `4a6a30897894df4c262f78d5d2d2dd1e87ea9b76`. That commit is negative evidence only and must not be accepted or copied wholesale.
- Previous failure classes: `scope_gate_failed`, broad legacy-directory Ruff failure, unauthorized `nexus/evidence/receipt_base.py`, caller-supplied bridge truth, symbol-only tests.
- Authority includes only Task3 producer-side bridge implementation, tests, scoped commit/Candidate, and independent physical verification.
- Excludes Task4 prerequisite/authority/signing, approval, integration, merge, push, PR, release, production, public protocol, Cloud/OIDC/RBAC, or commercial claims.
- `AUTO_CHAIN=false`.

## Required physical chain

`controller-frozen pre-execution context -> precompiled expected verifier contract -> real CandidateVerifier run_cli_worker execution -> raw CliWorkerResult capture at the execution seam -> canonical immutable artifact bytes -> controller-derived subject/producer/execution/attempt/environment bindings -> EvidenceSubmission -> unchanged ingest_evidence -> unchanged is_trusted_ingestion_result == True`

## Non-negotiable implementation requirements

1. `CandidateVerifier` must capture the actual `CliWorkerResult` immediately after `run_cli_worker(request)`. A wrapper that accepts caller-supplied `content`, `status`, `subject`, `requirement`, provenance, or a prebuilt receipt after `verify()` is forbidden.
2. Before execution, freeze an immutable bridge execution plan containing the expected verifier identity/status, exact controller subject inputs, producer profile identity, execution/attempt IDs, expected environment facts, canonical artifact encoding contract, locator, and any deterministic expected bytes/hash required by the pilot. It cannot inspect later output, ground truth, acceptance, certification, or observed PASS.
3. Derive observed status solely from physical process outcome. Required verifier exit `0` may yield observed `PASS`; nonzero, timeout, start failure, malformed/missing raw artifact, or binding mismatch yields no trusted bundle. Observed PASS cannot manufacture expected PASS.
4. Build raw artifact bytes deterministically from the actual result using a documented canonical encoding of stdout, stderr, exit code, status, and timeout. Exclude timing/PID fields from deterministic content unless prebound.
5. CAS must recompute SHA-256 from bytes, atomically create under a contained root, reject symlinks/path escape/oversize/empty/truncation/overwrite conflicts, fsync or equivalent durable close, read back, and rehash. Caller-supplied hashes are assertions only.
6. Controller subject binds repository, source/target revision and tree, ChangeSet/hash, diff hash, execution ID, attempt ID, and verifier ordinal/identity where applicable. Required hash/revision/tree formats are validated; no worker prose or caller-declared repository/revision becomes authority.
7. Producer identity/role/software hash/method are derived from the existing frozen Nexus-controlled trust profile and the physically observed executable identity/hash; no second registry or caller-created grant.
8. Environment fingerprint is deterministic, provider-neutral, secret-free, and derived from actual relevant facts. Missing/mismatched facts fail closed.
9. Construct only existing `ProvenanceEnvelope`, `EvidenceSubmission`, and `TrustedIngestionContext` inputs; call unchanged `ingest_evidence`, `classify_ingestion_result`, and `is_trusted_ingestion_result`. Never directly mint `EvidenceBundle`, `IngestionResult`, trusted receipt, or alternate classifier.
10. Provide one real prospective deterministic local verifier witness through `CandidateVerifier` that reaches trusted Task3 ingestion. Product-only fixtures, direct bridge calls, and mocked `run_cli_worker` are insufficient for the positive witness.
11. Do not construct or validate Task4 `TrustReference`, expectation, prerequisite, authority, policy, approval, issuer, signing, or certification semantics.

## Allowed repository paths

Production paths, maximum `6`:

- `nexus/orchestrator/candidate_verifier.py`
- `nexus/evidence/execution_subject.py`
- `nexus/evidence/environment_fingerprint.py`
- `nexus/evidence/artifact_store.py`
- `nexus/evidence/requirement_compiler.py`
- `nexus/evidence/product_ingestion_bridge.py`

Tests:

- `tests/nexus/evidence/test_producer_bridge.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`

Governance:

- `tasks/evidence-producer-bridge-20260830/INDEX.md`
- `tasks/evidence-producer-bridge-20260830/01-evidence-producer-bridge-r1.md`

Maximum changed paths: `10`.

## Forbidden scope

- `nexus/evidence/receipt_base.py` and every pre-existing `nexus/evidence/*` file not explicitly listed above.
- Any production mutation under `product/**`.
- Task4, certification/signing/authority, Planner/Workforce, lifecycle, standing grants, merge/release/production, provider adapters, or account credentials.
- Caller-supplied factual status, repository/revision/tree, trusted hash, producer/grant, environment hash, observed PASS, ground truth, evaluator output, historical outcome, certification disposition, or prior boolean.
- Symbol-only or import-only tests as behavioral evidence.
- Direct trusted-object minting, bypass of `ingest_evidence`, second classifier/registry/fallback, or provenance downgrade.

## Mandatory RED behavioral gates

Each test must execute behavior and fail for the intended reason before implementation; `hasattr`, import failure, fixture failure, or static symbol existence does not count:

1. no prospective capture path exists;
2. requirement/expected status must predate result;
3. artifact-byte substitution fails;
4. subject/revision/tree/diff substitution fails;
5. producer/software/method spoof fails;
6. execution/attempt replay fails;
7. environment substitution fails;
8. metadata with missing/raw bytes fails;
9. observed PASS cannot create expected PASS;
10. stale subject replay fails;
11. CAS symlink/path escape/overwrite conflict fails;
12. no direct trusted-object minting or bypass exists.

## Exact verification commands

- `uv run pytest -q tests/nexus/evidence/test_producer_bridge.py tests/nexus/orchestrator/test_candidate_verifier.py tests/product/test_trusted_evidence_ingestion.py`
- `uv run ruff check nexus/orchestrator/candidate_verifier.py nexus/evidence/execution_subject.py nexus/evidence/environment_fingerprint.py nexus/evidence/artifact_store.py nexus/evidence/requirement_compiler.py nexus/evidence/product_ingestion_bridge.py tests/nexus/evidence/test_producer_bridge.py tests/nexus/orchestrator/test_candidate_verifier.py`
- `uv run pyright nexus/orchestrator/candidate_verifier.py nexus/evidence/execution_subject.py nexus/evidence/environment_fingerprint.py nexus/evidence/artifact_store.py nexus/evidence/requirement_compiler.py nexus/evidence/product_ingestion_bridge.py`
- `git diff --check`
- Repeat the real prospective witness twice. Exact deterministic fields must match; generated execution/attempt/timestamp fields must be explicitly labelled and independently bound.
- Full path/deletion/mode audit and independent hostile acceptance.

## Exit

- Existing Task3 consumer remains byte-for-byte unchanged.
- Positive real witness returns trusted classification through unchanged Task3.
- All 12 behavioral hostile controls fail closed.
- No Task4 or parallel authority exists.
- Exact Candidate commit/tree/diff and independent acceptance recorded.
- Terminal: `EVIDENCE_PRODUCER_BRIDGE_VALIDATED`, then STOP.

`AUTO_CHAIN=false`
