# Campaign Index: ASTRA-P4-RUNTIME-QUALIFICATION-20260907

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Implement the first bounded prerequisite for the Owner-approved Astra P4 evidence-only canary: explicit NONCANONICAL_EVIDENCE_ONLY Task Card create/commit metadata support. Preserve default mutation-card semantics. Validate an exact external evidence_root under /private/tmp/astra-p4-realprovider-canary-20260907/ with path/traversal/symlink denial; evidence-only cards require empty product allowed_files and commit_required=false,candidate_required=false,worker_may_commit=false,worker_may_approve=false,worker_may_integrate=false,worker_may_push=false,AUTO_CHAIN=false. Coordinator may still commit exactly the card and INDEX. Bind contract kind and evidence root into owner effect authorization and public tool schema. Reject contradictory fields and ensure current worker_candidate/lifecycle ingress cannot interpret this metadata-only card as source-write permission. This repair itself is a normal source-changing governed Candidate, not an evidence-only execution. Do not implement evidence execution or claim the P4 canary complete. Freeze controller source at actual card commit; preserve qualified Astra subject 4887d8f6a3faf50d6b600f2c170526e08d4bf408 separately. Luna implements only listed files; independent root verification required. No merge, deployment, active writer migration, protected grant edits, or self-approval.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-readonly-card-contract-repair-20260907` | `00-astra-readonly-card-contract-repair-20260907.md` | ACTIVE | Owner confirmation |
