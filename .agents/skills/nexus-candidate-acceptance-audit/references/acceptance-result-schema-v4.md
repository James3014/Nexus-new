# Nexus Candidate Acceptance Result v4

Canonical schema: `nexus.candidate_acceptance.v4`.

v4 deliberately preserves `nexus.candidate_acceptance.v3` as a historical compatibility contract. Do not rewrite v3 artifacts into v4 or claim that a v4 discriminator retroactively repairs missing executor lineage.

## Evidence unions

`source.executor_evidence_kind` is exactly one of:

- `NEXUS_MCP_RECEIPT`
- `DEVSPACE_DIRECT_EVIDENCE`

`source.executor_evidence_sha256` binds the exact physical executor-evidence bytes.

`source.verification_evidence_kind` is exactly one of:

- `MCP_VERIFIED_RECEIPT`
- `CORE_GENERIC_VERIFICATION_RESPONSE`

`source.verification_evidence_sha256` binds the exact physical verification-evidence bytes.

The discriminator selects a validation branch only. It does not grant execution, verification, certification, acceptance, approval, merge, release, or Owner authority.

## DEVSPACE_DIRECT_EVIDENCE branch

Require `contract_kind=OWNER_INLINE`. The physical `devspace.direct_candidate_execution.v1` evidence is the source of task, attempt, contract and Candidate lineage. If the exact physical producer artifact is absent, formal v4 acceptance is `ACCEPTANCE_BLOCKED`; Core session state, CI, PR metadata, or controller prose must not be promoted into substitute executor evidence. Do not create or require synthetic campaign, Task Card, compiled packet, MCP execution manifest or MCP receipt fields for this branch. These fields remain `null` where the v4 result retains them for cross-branch shape compatibility.

Cross-bind at minimum:

- `source.task_id` -> `authority.task_id`
- `source.implementer_attempt_id` -> `authority.attempt_id`
- `source.contract_hash` -> the hex body of `core_binding.acceptance_contract_hash`
- repository root -> `execution.workspace_root`
- expected base / executor-observed head -> `candidate.source_commit`
- Candidate commit/tree -> `candidate.commit_sha` / `candidate.tree_sha`
- Candidate diff -> the hex body of `candidate.diff_hash`
- source/target trees -> physical `candidate.change_manifest`

The committed producer uses `integrity.sha256` only. Compute it over the producer-canonical document with `integrity.sha256` replaced by 64 zeroes; do not accept an alternate `algorithm/hash` integrity object as the same contract. `authority.dispatch_intent` must first survive the committed producer parser/validator semantics, must equal the producer-normalized object emitted by `parseDispatchIntent`, and only then is its producer-canonical representation hashed and cross-bound to task/attempt/Core authority. Re-normalizing attacker-supplied evidence and accepting the normalized projection is not equivalent to validating producer output. Replay JavaScript `String.prototype.trim()` exactly for producer text normalization; Python `str.strip()` is not equivalent for all Unicode whitespace. Execution identity/timestamps and `execution_generation` must likewise satisfy the committed producer contract rather than merely agree with caller-supplied hashes. The generation object uses the committed `ExecutionGenerationBinding` shape: `model` and `runtimeVersion` are optional producer fields, a non-null projected execution model requires the same generation model, and `capabilitySurfaceDigest` is derived from the committed `resolveExecutionGeneration` inputs. Recompute the deterministic evidence id, require the committed `cms_<32hex>` Core session identity, bind `created_at` to Candidate provenance, and recompute the embedded `core_binding.binding_hash`, Core workspace identity and AcceptanceContract hash from their committed canonical forms; internal field agreement alone is not proof.

`candidate.change_manifest` is the Core manifest object `{source_tree,target_tree,entries}`. New v4 direct evidence orders entries by Unicode code-point lexical path order, exactly matching canonical Nexus Core `sorted(..., key=path)` semantics and the repaired DevSpace producer contract. `candidate.diff_hash` is the Core canonical hash of `nexus.core.git-change-manifest.v1-experimental` plus those exact source/target trees and canonically ordered entry tuples. It is not a raw `git diff` byte hash. A validator must rebuild the manifest from immutable Git objects, require the physical Git origin to match the embedded Core repository origin under Core normalization, require every physical changed path to be contained by the bound AcceptanceContract `allowed_paths`, enforce `deletion_policy=FORBID`, and recompute the manifest hash. Matching forged values in executor evidence, Core binding and the acceptance result therefore still fail closed. JavaScript remains required where producer parity depends on JavaScript-specific object canonicalization, trimming, date parsing, or execution-generation semantics; manifest path ordering itself is no longer locale-dependent.

The direct evidence must remain a pending-Candidate producer artifact: `status=CANDIDATE_CAPTURED_PENDING_CORE_VERIFICATION_AND_ACCEPTANCE`, `claim_ceiling=CANDIDATE_READY`, and `core_verified=false`, `certified=false`, `accepted=false`, `approved=false`, `merged=false`, `released=false`, `deployed=false`, and `public_claim_allowed=false`.

For this branch, `verification_evidence_kind` must be `CORE_GENERIC_VERIFICATION_RESPONSE`. Require schema `nexus.core.generic-verification-response.v1-experimental` and its exact committed nested shape: `verification={status,reason_codes,integrity}`, with `VERIFIED`, empty `reason_codes`, and `integrity=VALID`; exactly five committed `hashes`; and only null or schema-valid `{disposition,receipt}` certification. Require an exact AcceptanceContract-hash match and exact Core change-manifest-hash match to the direct evidence. Core verification remains factual verification only. Any separate `certification` member does not become Candidate Acceptance authority.

`candidate_state_hash` and `verified_receipt_hash` may be `null` only on this branch when the direct producer does not physically expose those subjects. Null must never be replaced with invented values.

### Historical v4 direct-evidence replay

Historical direct-evidence v4 material bound to skill revision `2026-09-15-v4-tgb` is replayed with `scripts/validate_acceptance_result_v4_legacy_20260915.py` and the archived `references/acceptance-result-schema-v4-legacy-20260915.md`. New evidence must never select that historical locale-order contract, and historical material must not be silently reinterpreted under the current canonical-order validator.

## NEXUS_MCP_RECEIPT branch

This branch preserves v3 MCP executor semantics. `verification_evidence_kind` must be `MCP_VERIFIED_RECEIPT`. The historical v3 validator remains the compatibility oracle for Task Card / Owner-inline contract, packet, manifest, executor receipt, runtime Workforce Admission, Candidate identity, authority and claim-ceiling checks.

A v4 MCP result must additionally hash-bind the physical executor evidence and physical verification evidence. The report must be an emitted historical v3 validator report; the v4 validator re-runs the unchanged v3 oracle against the exact projected result and physical receipt, so a forged minimal `valid=true` object is invalid. The v4 discriminator is not permission to weaken any v3 gate.
## Acceptance and authority invariants

The six evidence axes, reviewer independence, materially independent oracle, exact Candidate identity, exact-base differential classification, approval-readiness separation and claim discipline remain mandatory.

`ACCEPT_CANDIDATE` is only a recommendation about the frozen Candidate. It never implies certification, Owner approval, integration, merge, release, deployment or a public claim.

Keep `approval_boundary.acceptance_recommendation_only=true`, `owner_action_required=true`, and all approval/integration/public-claim booleans false.

All six evidence axes are mandatory. `maximum_supportable_claim` must not carry certification, Owner approval, merge, release, deployment, production-readiness, or public-claim escalation. Malformed nested evidence fails closed with a structured validation report and exit status 2.

A physical mismatch may be represented by a machine-valid negative result only when the corresponding axis is explicitly `FAIL` or `BLOCKED`; the same mismatch must fail closed for `ACCEPT_CANDIDATE`.

## Validators

Historical v3 artifacts continue to use:

```bash
python -B scripts/validate_acceptance_result.py acceptance-result-v3.json ...
```

v4 artifacts use:

```bash
python -B scripts/validate_acceptance_result_v4.py acceptance-result-v4.json \
  --executor-evidence executor-evidence.json \
  --verification-evidence verification-evidence.json \
  --report acceptance-v4.validation.json
```

For `NEXUS_MCP_RECEIPT`, also supply `--v3-validation-report` from the unchanged v3 compatibility validation. A structurally valid v4 document without its required physical evidence is not acceptance evidence.


## v5 successor / compatibility contract

`nexus.candidate_acceptance.v5` is the successor schema for **GOVERNED**
Candidate Acceptance when the physical executor is transport-neutral and is not
truthfully represented by the Nexus MCP or DevSpace-specific v4 branches.

This section does **not** change `nexus.candidate_acceptance.v4`. Every v4
input continues through the saved current v4 implementation, and historical
`2026-09-15-v4-tgb` material continues through its frozen legacy validator.
The v5 implementation shares
`scripts/validate_acceptance_result_v4.py` only because the governed execution
surface used for #1176 could not create a new validator target file. Schema
dispatch preserves the v4/v5 semantic boundary.

v5 does not create a new authority source. A v5 transport-neutral acceptance
attempt must already be GOVERNED and must bind a physical Git-tracked Task Card
that exists in the authorized base commit.

For v5:

- `source.contract_kind = TRACKED_TASK_CARD`
- `source.campaign_id` is non-empty
- `source.task_card_path` is non-empty
- `source.task_card_sha256` is the SHA-256 of the Task Card bytes read from
  `expected_base_commit:task_card_path`
- `source.contract_hash = source.task_card_sha256`
- `source.executor_evidence_kind = TRANSPORT_NEUTRAL_DIRECT_EVIDENCE`
- executor schema = `nexus.transport_neutral_direct_execution.v1`
- `source.verification_evidence_kind = INDEPENDENT_REVIEW_EVIDENCE`
- review schema = `nexus.independent_candidate_review_evidence.v1`
- compiled-packet and MCP execution-manifest compatibility fields remain null
- `candidate_state_hash` and `verified_receipt_hash` remain null when the
  transport-neutral producer does not physically expose those subjects.

The discriminator selects validation logic only. Codex, RDC, DevSpace, another
CLI, or a human operator is an observed executor/transport identity, not an
authority source or route selector.

### Tracked Task Card authority

The validator reads the Task Card bytes from the exact authorized base commit.
It does not trust a path or hash supplied only by the executor artifact.

The physical Task Card must:

- have the same `task_id`;
- have `artifact_authority: current` and `status: ACTIVE`;
- require a commit and Candidate;
- keep `worker_may_approve`, `worker_may_integrate`, and
  `worker_may_push` false;
- keep `AUTO_CHAIN: false`;
- expose a non-empty exact Allowed files list; and
- bind deletion policy explicitly when present, otherwise default to
  `FORBID`.

The Task Card SHA-256, task ID, allowed paths, and deletion policy must
cross-bind the acceptance result and executor evidence. Rewriting executor JSON
and recomputing its integrity cannot widen the Task Card scope.

### Transport-neutral direct executor evidence

`nexus.transport_neutral_direct_execution.v1` has exact top-level groups:

    schema
    evidence_id
    created_at
    authority
    execution
    candidate
    claim
    integrity

`authority` binds the already-existing governed contract:

    contract_kind = TRACKED_TASK_CARD
    task_id
    attempt_id
    task_card_path
    task_card_sha256
    allowed_paths[]
    deletion_policy = ALLOW | FORBID
    claim_ceiling = CANDIDATE_READY

`execution` records observations only:

    executor_id
    executor_kind
    transport
    workspace_root
    started_at
    completed_at
    state = completed
    terminal_reason = completed

None of those execution fields grants authority.

`candidate` binds the physical Git subject:

    repository_origin
    source_commit
    commit_sha
    tree_sha
    changed_paths[]
    deleted_paths[]
    change_manifest
    diff_hash

The validator resolves the exact Git objects, verifies ancestry, rebuilds the
manifest, compares the physical origin and tree, recomputes the Core manifest
hash, and enforces the Task Card's allowed paths and deletion policy. A
self-consistent executor JSON document cannot replace those physical checks.

The executor claim remains Candidate evidence only:

    status = CANDIDATE_READY_PENDING_ACCEPTANCE
    claim_ceiling = CANDIDATE_READY
    verified = false
    certified = false
    accepted = false
    approved = false
    merged = false
    released = false
    deployed = false
    public_claim_allowed = false

`integrity.sha256` is the canonical SHA-256 of the exact evidence object with
that field replaced by 64 zeroes.

### Independent review evidence and provenance

`nexus.independent_candidate_review_evidence.v1` binds the exact reviewer
attempt, repository, base, Candidate commit/tree, command results, claim
ceiling, and provenance. At least one command must be a PASS with exit code 0
when the acceptance result claims independent-behavior PASS.

The review artifact includes a `provenance` object:

    kind = GITHUB_ISSUE_COMMENT
    repository_full_name
    issue_number
    comment_id
    author_login
    review_record_sha256
    body_sha256

The review-record hash covers reviewer identity/attempt, independence class,
exact repository/Candidate binding, commands and claim. The validator then
re-reads the GitHub comment through authenticated `gh api` and requires:

- the live comment author to equal `author_login`;
- `reviewer_id` to equal that authenticated GitHub author;
- the comment repository to match the Candidate origin;
- the exact issue binding and exact body hash; and
- exact body markers for `review_record_sha256`, Candidate SHA, Task Card
  SHA-256, reviewer attempt, and reviewer ID.

If that live provenance cannot be re-read or does not match, v5 fails closed.
The GitHub comment is evidence publication, not Candidate Acceptance, Owner
approval, merge, release, deployment, routing, Workforce, certification, or
public-claim authority.

The review claim ceiling remains:

    claim_ceiling = INDEPENDENT_BEHAVIOR_EVIDENCE_ONLY
    certified = false
    accepted = false
    approved = false
    merged = false
    released = false
    deployed = false
    public_claim_allowed = false

### v5 result and compatibility projection

The v5 result preserves the v4 result envelope and six independent evidence
axes. The validator may create an in-memory v4 compatibility projection solely
to reuse unchanged envelope checks. That projection deliberately removes v5
Task Card lineage and substitutes the v4 direct discriminator only in memory.

The projection:

- is never emitted as evidence;
- never creates real DevSpace lineage;
- never rewrites a historical artifact;
- never changes the actual v5 integrity hash; and
- cannot be used as acceptance, approval, or merge provenance.

The actual v5 result and both physical evidence files remain independently
SHA-256-bound.

### DIRECT and GOVERNED remain separate

v5 does not change repository execution-lane policy.

Eligible `DIRECT_CANONICAL` and `DIRECT_DELEGATED` work remains subject to
its existing direct verification and Owner merge gates. It does not acquire a
formal v5 Candidate-Acceptance requirement merely because Codex, RDC, or
another transport was used.

`GOVERNED` work still requires independent Candidate Acceptance and
machine-verifiable provenance where the current repository contract requires
them. v5 only lets that governed acceptance consumer ingest truthful
transport-neutral execution evidence without relabeling it as DevSpace.

### Current invocation path

For both current v4 and v5, invoke the schema-dispatch wrapper:

```bash
python -B scripts/validate_acceptance_result_v4.py acceptance-result.json \\
  --executor-evidence executor-evidence.json \\
  --verification-evidence verification-evidence.json \\
  --report acceptance.validation.json
```

The result schema determines whether the saved v4 implementation or the v5
transport-neutral governed branch is used.
