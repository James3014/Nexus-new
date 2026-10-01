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

Require `contract_kind=OWNER_INLINE`. The physical `devspace.direct_candidate_execution.v1` evidence is the source of task, attempt, contract and Candidate lineage.Do not create or require synthetic campaign, Task Card, compiled packet, MCP execution manifest or MCP receipt fields for this branch. These fields remain `null` where the v4 result retains them for cross-branch shape compatibility.

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

`candidate.change_manifest` is the Core manifest object `{source_tree,target_tree,entries}`. The committed producer orders entries with `entry.path.localeCompare(...)`; code-point sorting is not an equivalent substitute. `candidate.diff_hash` is the Core canonical hash of `nexus.core.git-change-manifest.v1-experimental` plus those exact source/target trees and producer-ordered entry tuples. It is not a raw `git diff` byte hash. A validator must rebuild the manifest from immutable Git objects, require the physical Git origin to match the embedded Core repository origin under Core normalization, require every physical changed path to be contained by the bound AcceptanceContract `allowed_paths`, enforce `deletion_policy=FORBID`, and recompute the manifest hash. Matching forged values in executor evidence, Core binding and the acceptance result therefore still fail closed. Direct validation requires a Node runtime to replay these producer ordering/canonicalization semantics; if that capability is missing, validation blocks rather than guessing.

The direct evidence must remain a pending-Candidate producer artifact: `status=CANDIDATE_CAPTURED_PENDING_CORE_VERIFICATION_AND_ACCEPTANCE`, `claim_ceiling=CANDIDATE_READY`, and `core_verified=false`, `certified=false`, `accepted=false`, `approved=false`, `merged=false`, `released=false`, `deployed=false`, and `public_claim_allowed=false`.

For this branch, `verification_evidence_kind` must be `CORE_GENERIC_VERIFICATION_RESPONSE`. Require schema `nexus.core.generic-verification-response.v1-experimental` and its exact committed nested shape: `verification={status,reason_codes,integrity}`, with `VERIFIED`, empty `reason_codes`, and `integrity=VALID`; exactly five committed `hashes`; and only null or schema-valid `{disposition,receipt}` certification. Require an exact AcceptanceContract-hash match and exact Core change-manifest-hash match to the direct evidence. Core verification remains factual verification only. Any separate `certification` member does not become Candidate Acceptance authority.

`candidate_state_hash` and `verified_receipt_hash` may be `null` only on this branch when the direct producer does not physically expose those subjects. Null must never be replaced with invented values.

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
