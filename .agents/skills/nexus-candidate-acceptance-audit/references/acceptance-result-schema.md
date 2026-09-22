# Nexus Candidate Acceptance Result v3

Canonical schema: `nexus.candidate_acceptance.v3`.

The result is an independent Candidate recommendation. It never creates an approval contract, approves, integrates, pushes, disposes, cleans up, releases, or authorizes a public claim.

## Top-level structure

Require:

- `acceptance_id`, `created_at`, `verdict`;
- `source`: contract and task/attempt/executor lineage;
- `repository`: immutable Candidate and audit start/end repository identity;
- `transport`: Gateway, action, permission, host-binding, and verification-surface evidence;
- `axes`: six independent evidence axes;
- `review`: reviewer independence, exact commands, anti-false-green result, and transport failures;
- `approval_readiness`: separate readiness for a future owner approval action;
- `approval_boundary`: explicit non-approval and non-integration values;
- `maximum_supportable_claim`, `next_gate`, `blockers`, and `integrity`.

Do not add dynamic executor/workforce fields to this schema merely to mirror upstream changes. Bind them as physical validation side evidence unless/until the canonical acceptance schema is deliberately versioned.

## Contract lineage

`source.contract_kind` is exactly one of:

- `TRACKED_TASK_CARD`: require `campaign_id`, `task_card_path`, and `task_card_sha256`; use the universal `contract_hash`.
- `OWNER_INLINE`: require `contract_hash`; require `task_card_path=null` and `task_card_sha256=null`; `campaign_id` may be null.

Both require one stable `task_id`, implementer attempt, reviewer attempt, and executor-receipt digest. Compiled packet and execution manifest digests are nullable only when those upstream artifacts genuinely do not exist.

Current upstream executor lineage is:

- packet: `nexus.compiled_model_task_packet.v3` when present;
- manifest: `nexus.chatgpt_mcp_execution.v4`;
- receipt: `nexus.mcp_execution_receipt.v2`.

Manifest v3 / receipt v1 may be read as historical compatibility evidence, but validation must report the legacy lineage and must not silently promote it to current evidence.

For a current model-specific `COMPILED_PACKET` receipt, execution-time Workforce Admission is validation side evidence. Require a physical runtime-admission document and validate it against the physical packet when exact worker/model binding is material. Compile-time admission inside the packet does not substitute for execution-time admission.

## Candidate and transport clocks

Repository identity records:

- audit start/end HEAD;
- expected base;
- Candidate commit/tree/state/diff;
- verified-receipt hash;
- dirty-state description;
- whether the Candidate was already integrated;
- whether repository/Candidate identity materially drifted during the audit.

Use only full Git OIDs: exactly 40 lowercase hexadecimal characters for SHA-1 objects or exactly 64 for SHA-256 objects. Do not accept 41-63-character pseudo-OIDs as immutable subjects.

Transport identity records:

- mode: `LIVE_MCP`, `LOCAL_READ_ONLY`, or `SOURCE_BOUNDED`;
- server instance and canonical root when applicable;
- action contract, tool manifest, full schema, lifecycle, and permission policy;
- host-binding and safe verification-surface classification;
- reload/review/runtime-source state;
- start/end evidence references and transport stability.

Nullable transport identity fields are allowed only when the mode does not expose them. Null means unknown or not applicable, never verified clean.

Treat latest target/base branch advancement separately from `repository_drift_during_audit`. If the frozen Candidate subject remains unchanged, target advancement may require later integration revalidation without invalidating base-relative Candidate acceptance.

## Independent behavior and oracle provenance

The v3 JSON keeps reviewer independence in `review.independence_class`; record oracle provenance in the human report/evidence references rather than silently expanding the schema.

`ACCEPT_CANDIDATE` requires:

- `review.independence_class=INDEPENDENT_REVIEWER`;
- at least one PASS command when independent behavior is required;
- a materially independent oracle: contract-defined, pre-existing, or independently authored evidence sufficient for the claim.

If all decisive behavioral assertions/witnesses are Candidate/implementer-authored and no independent oracle exists, report at most `PARTIAL_INDEPENDENCE` and block acceptance or route deep evidence review to `nexus-test-quality-audit`.

For reproducible bug fixes, record paired base/Candidate replay in evidence references when available. The schema does not add special replay fields in v3.


## Exact-base differential and integration-subject side evidence

Keep `nexus.candidate_acceptance.v3` stable. Record exact-base comparison and integration-context subjects in the human report and evidence references rather than adding new top-level schema fields.

Use these differential classifications:

- `BASELINE_PASS_CANDIDATE_PASS`;
- `CANDIDATE_IMPROVEMENT`;
- `EXACT_BASELINE_DEBT`;
- `CANDIDATE_REGRESSION`;
- `NON_COMPARABLE_BASELINE`;
- `INFRASTRUCTURE_OR_POLICY_VARIANCE`.

`EXACT_BASELINE_DEBT` means the same material failure is reproduced on the exact expected base and exact Candidate under a materially equivalent verifier environment. It is not a PASS. Positive acceptance may coexist with it only when current contract/policy explicitly allows baseline debt and Candidate-specific required behavior remains independently proven.

Keep CI/check subjects distinct:

- `CANDIDATE_HEAD` — the immutable Candidate being accepted;
- `MERGE_GROUP` — a temporary integration subject that may include a newer base and other queued changes;
- `POST_MERGE_MAIN` — the resulting integrated repository subject.

Evidence about `MERGE_GROUP` or `POST_MERGE_MAIN` cannot fill missing Candidate contract, attempt, executor, oracle, or identity evidence. Likewise Candidate acceptance cannot stand in for later integration revalidation.

## Candidate verdict versus approval readiness

Candidate verdicts:

- `ACCEPT_CANDIDATE`: every required axis passed and reviewer/oracle independence is sufficient.
- `REJECT_CANDIDATE`: at least one required axis failed.
- `ACCEPTANCE_BLOCKED`: required evidence or independent verification is unavailable.
- `OWNER_DECISION_REQUIRED`: evidence is coherent but owner policy is unresolved.

Approval-readiness states:

- `READY_FOR_OWNER_APPROVAL`
- `BLOCKED_BY_TRANSPORT_FRESHNESS`
- `BLOCKED_BY_HOST_BINDING`
- `BLOCKED_BY_LIFECYCLE_STATE`
- `NOT_EVALUATED`

An accepted Candidate may have a blocked approval gate. Approval-readiness blockers belong inside `approval_readiness.blockers`; top-level `blockers` describe Candidate acceptance blockers only.

Keep these false:

- `approval_boundary.candidate_approved`
- `approval_boundary.approval_contract_created`
- `approval_boundary.integrated`
- `approval_boundary.public_claim_allowed`

Keep `approval_boundary.acceptance_recommendation_only=true` and `owner_action_required=true`.

## Physical findings in negative results

A physical mismatch is evidence, not necessarily a malformed acceptance document.

Validation may allow a physical mismatch as a warning only when:

- the top-level verdict is not `ACCEPT_CANDIDATE`; and
- the evidence axis named by the mismatch is explicitly `FAIL` or `BLOCKED`.

Examples:

- runtime Workforce Admission mismatch + `authority=FAIL` + `REJECT_CANDIDATE` may be a valid negative result;
- missing runtime admission + `authority=BLOCKED` + `ACCEPTANCE_BLOCKED` may be a valid blocked result;
- the same mismatch inside `ACCEPT_CANDIDATE` is always invalid.

This permits machine-valid rejection/block receipts without weakening positive acceptance.

## Integrity and physical binding

Compute `integrity.sha256` from sorted compact JSON with `integrity.sha256` temporarily set to 64 zeroes. This proves document consistency only.

Validate against physical upstream artifacts when available:

```bash
python -B scripts/validate_acceptance_result.py acceptance-result.json \
  --task-card TASK-CARD.md \
  --compiled-packet packet.json \
  --execution-manifest execution-manifest.json \
  --executor-receipt execution-receipt.json \
  --runtime-admission runtime-workforce-admission.json \
  --report acceptance.validation.json
```

For a current `COMPILED_PACKET` Candidate, require `--runtime-admission`. Omit it for non-compiled execution or when exact model binding is genuinely not applicable. Passing a sidecar where it is inapplicable is itself a binding error.

The validator checks duplicate keys, safe regular-file binding, document integrity, contract-kind consistency, Git OID form, current/legacy executor lineage, packet/manifest/receipt physical hashes, Candidate identity, receipt authority/claim ceilings, and runtime Workforce Admission binding when applicable.

Missing physical arguments produce warnings only when the corresponding source is legitimately absent. A structurally valid result is never by itself proof of physical acceptance.
