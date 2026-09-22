# Nexus Candidate Acceptance Audit v4 overlay

This overlay applies when producing or validating `nexus.candidate_acceptance.v4`. Read the complete shared `PROCEDURE.md` first; every authority, independence, exact-subject, anti-false-green, approval-readiness and stop rule remains binding unless this overlay explicitly versions the artifact contract.

Read additionally:

- `references/acceptance-result-schema-v4.md`
- `references/acceptance-template-v4.md`
- `references/schema-compatibility.md`

v3 remains historical compatibility. Replay historical `nexus.candidate_acceptance.v3` artifacts only under the unchanged v3 semantics. Never rewrite a v3 artifact into v4, create a generic v3-to-v4 migration/projection artifact merely to upgrade it, or fill missing historical lineage. A `nexus.candidate_acceptance.v4` artifact is valid only for a genuinely new acceptance attempt backed by current physical v4 evidence, and that new evidence must not be represented as evidence from the historical v3 attempt.

Historical direct-evidence v4 material created under skill revision `2026-09-15-v4-tgb` must be replayed with `scripts/validate_acceptance_result_v4_legacy_20260915.py`. New v4 attempts use the current validator and canonical Nexus Core path ordering. Do not reinterpret a locale-ordered historical artifact with the current validator, and do not use the legacy validator for new evidence.

## 1. Freeze the v4 evidence union

Before physical validation, record:

- `executor_evidence_kind`
- exact `executor_evidence_sha256`
- `verification_evidence_kind`
- exact `verification_evidence_sha256`
- immutable Candidate commit/tree/base
- implementer and reviewer attempts

Allowed executor branches are only `NEXUS_MCP_RECEIPT` and `DEVSPACE_DIRECT_EVIDENCE`. Allowed verification branches are only `MCP_VERIFIED_RECEIPT` and `CORE_GENERIC_VERIFICATION_RESPONSE`.

The discriminator selects validation logic only. It is not an authority selector.
## 2. NEXUS_MCP_RECEIPT

Preserve all v3 Task Card / Owner-inline, compiled packet, manifest, executor receipt, runtime Workforce Admission, Candidate identity, authority and claim-ceiling checks.

Run the unchanged v3 validator against the physical v3-compatible acceptance inputs and retain its validation report. Then run the v4 validator with the physical executor evidence, physical MCP verified receipt and the v3 validation report.

A v4 MCP result is invalid if the v3 compatibility report is absent or not valid. The report must have the exact historical validator output shape; v4 re-runs the unchanged v3 oracle against a v3 projection of the exact result and physical MCP receipt, so a minimal forged `valid=true` object is not sufficient. v4 may add physical digest binding; it may not subtract a v3 gate.

## 3. DEVSPACE_DIRECT_EVIDENCE

Require the physical executor document to be `devspace.direct_candidate_execution.v1` and `contract_kind=OWNER_INLINE`. If that physical producer artifact does not exist for the exact Candidate, return `ACCEPTANCE_BLOCKED`; do not synthesize executor evidence from Core session rows, CI, PR metadata, or controller prose. Producer availability is owned by the DevSpace producer contract, not by this acceptance consumer.

Do not invent campaign, Task Card, compiled packet, MCP manifest or MCP receipt lineage. Require those compatibility fields to remain null.

Cross-bind the physical evidence to the result using the immutable TG-A producer contract:

- task and implementer attempt from `authority.task_id` / `authority.attempt_id`
- AcceptanceContract hash from `core_binding.acceptance_contract_hash`
- workspace root from `execution.workspace_root`
- source/base commit from `candidate.source_commit`
- Candidate commit and tree from `candidate.commit_sha` / `candidate.tree_sha`
- Candidate diff from `candidate.diff_hash`
- source/target tree in the physical `candidate.change_manifest`

Require direct evidence integrity in the producer form `integrity.sha256`, computed with that field replaced by 64 zeroes using the committed producer's recursive JSON object-key `localeCompare` ordering; this is distinct from Core change-manifest path ordering. Do not accept alternate integrity field names as compatibility aliases. Parse and validate `authority.dispatch_intent` with the committed DispatchIntent semantics before recomputing its hash: required text, role/claim enums, array normalization, scope rules, boolean types, acceptance criteria and exclusive-ownership/mutation coupling all remain binding. The physical evidence must already equal the object emitted by committed `parseDispatchIntent`; normalization is not permission to accept a non-normalized evidence object whose hash is recomputed over the normalized projection. Replay JavaScript `String.prototype.trim()` exactly for producer-normalized text; Python `str.strip()` is not equivalent (`U+FEFF` is trimmed by JavaScript while `U+0085` is not). Recompute the embedded Core mutation `binding_hash`, AcceptanceContract hash and Core `workspace_identity` from their canonical committed forms instead of accepting self-consistent supplied hashes.

Require the committed execution identity contract as well as terminal state: producer-trim non-empty agent/profile/provider/workspace identity, nullable-or-non-empty optional model/session fields, present producer-parseable start/completion timestamps, `terminal_reason=completed`, and a recomputed execution-generation hash that cross-binds the projected execution. `execution_generation` must match the committed `ExecutionGenerationBinding` shape; `model` and `runtimeVersion` may be omitted only where the producer can omit them, a non-null projected execution model must be present and equal in the generation binding, and `capabilitySurfaceDigest` must be recomputed from the committed `resolveExecutionGeneration` inputs. Recompute the deterministic `dce_<32hex>` evidence id, require the `cms_<32hex>` Core session identity, and require top-level `created_at` to equal `candidate.provenance_created_at`. Require durable state `completed`, `WITHIN_SCOPE`, `retry_safe=false`, and `reconciliation_required=false`.

Require a non-empty structurally valid Core change manifest with unique repository-relative paths and valid Git object/mode transitions. Its source tree must be `git-tree:<source_commit>` and target tree `git-tree:<tree_sha>`. Rebuild it from immutable Git commits and ancestry rather than trusting supplied JSON, and require the physical Git `origin` to match the embedded Core repository origin under the committed Core remote-normalization rule. Every physical changed path must be contained in the bound AcceptanceContract `allowed_paths`, and physical deletions must fail when `deletion_policy=FORBID`; self-consistent rewritten contract hashes do not override these Core scope invariants. For new v4 direct evidence, order manifest entries by Unicode code-point lexical path order, exactly matching canonical Nexus Core `sorted(..., key=path)` semantics and the repaired DevSpace producer contract. Recompute `candidate.diff_hash` as the Core canonical hash over `nexus.core.git-change-manifest.v1-experimental`, source tree, target tree and those canonically ordered entry tuples; it is not the SHA-256 of raw `git diff` output. JavaScript runtime parity is still required where the committed direct-evidence producer uses JavaScript-specific object canonicalization, `String.prototype.trim()`, date parsing, or execution-generation semantics, but manifest path ordering itself is no longer locale-dependent.

Require the producer claim to remain `CANDIDATE_READY` and pending Core verification / Candidate Acceptance. Every certification, acceptance, approval, merge, release, deployment and public-claim flag must remain false.
## 4. CORE_GENERIC_VERIFICATION_RESPONSE

Require schema `nexus.core.generic-verification-response.v1-experimental` and the exact committed response shape. `verification` must contain only `status`, `reason_codes`, and `integrity`; `VERIFIED` requires `reason_codes=[]` and `integrity=VALID`. `hashes` must contain exactly the five committed Core hash fields. `certification` may be null or the committed `{disposition,receipt}` shape only.

Hash-bind the exact response bytes. Cross-bind `hashes.acceptance_contract_hash` to the direct evidence Core binding and recompute the Core generic change-manifest hash from the physical direct evidence. It must equal `hashes.change_manifest_hash`.

Core VERIFIED proves only the Core verification fact for the bound ChangeSet evidence. It does not prove certification or Candidate acceptance. If the Core response contains separate certification material, record it separately and do not inherit its authority.

## 5. Independent acceptance remains unchanged

After executor and Core/MCP verification lineage passes, perform the shared procedure's independent behavior review. `ACCEPT_CANDIDATE` still requires an independent reviewer and a materially independent oracle. Producer evidence and Core verification are inputs to acceptance, not substitutes for independent acceptance.

Keep exact-base debt, CI subject roles, merge-group/post-merge separation, provenance policy and owner-approval readiness exactly as defined in `PROCEDURE.md`.

All six evidence axes are mandatory in v4. The maximum supportable claim must not escalate to certification, Owner approval, merge, release, deployment, production readiness or a public claim. Malformed nested evidence fails closed with a structured report and exit status 2.

## 6. Validate and stop

For v4:

```bash
python -B scripts/validate_acceptance_result_v4.py acceptance-result-v4.json \
  --executor-evidence executor-evidence.json \
  --verification-evidence verification-evidence.json \
  --report acceptance-v4.validation.json
```

For the MCP branch, also provide `--v3-validation-report acceptance-v3.validation.json` from the unchanged v3 validator.

Return the v4 human report, machine result, validation report, exact physical artifact digests, one next gate and prohibited next actions. Do not approve, integrate, merge, release, install another skill, or auto-chain.
