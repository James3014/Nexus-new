# Nexus Candidate Acceptance Audit

## 1. Acceptance contract

- Contract kind: `TRACKED_TASK_CARD | OWNER_INLINE`
- Campaign/task ID:
- Task Card path/hash, or Owner-inline `contract_hash`/expiry:
- Implementer attempt:
- Reviewer attempt and independence class:
- Expected base:
- Candidate commit/tree/state/diff/verified-receipt hashes:
- Executor lineage: packet / manifest / receipt schemas and digests:
- Runtime Workforce Admission side evidence, if applicable:
- Evidence cutoff and mode:
- Maximum supportable claim:

## 2. Freshness and transport

| Field | Start | End | Status | Evidence |
|---|---|---|---|---|
| Repository root/branch/HEAD/dirty | | | | |
| Durable task status and attempt | | | | |
| Candidate exact binding | | | | |
| Expected base / current target context | | | | |
| Server instance/canonical root | | | | |
| Action contract/tool manifest/full schema | | | | |
| Lifecycle/permission policy | | | | |
| Runtime/reload/action/permission review | | | | |
| Host-bound action surface | | | | |
| Safe verification surface | | | | |

Transport failure class: `NONE | HOST_ACTION_BINDING_GAP | ACTION_RESOLUTION_FAILURE | SERVER_ACTION_NOT_FOUND | TRANSPORT_CAPABILITY_GAP | TRANSPORT_AVAILABILITY_FAILURE | TRANSPORT_DEFINITION_DRIFT`

Integration-context note: state whether target/base advanced after the frozen Candidate was created. Do not silently rewrite the Candidate.

## 3. Frozen subject set

| Subject class | Immutable identifier | Expected source/policy | Observed | Status | Evidence |
|---|---|---|---|---|---|
| Contract/task/attempt | | | | | |
| Candidate commit/tree/state/diff | | | | | |
| Packet/manifest/executor receipt | | | | | |
| Runtime Workforce Admission | | | | | |
| Build/release artifact | | | | | |
| Test/log/result artifact | | | | | |
| Attestation bundle | | | | | |

## 4. Evidence-axis verdicts

| Axis | Required | Observed | Verdict | Evidence |
|---|---|---|---|---|
| Authority | | | | |
| Subject identity | | | | |
| Lineage | | | | |
| Independent behavior | | | | |
| Provenance/attestation | | | | |
| Claim discipline | | | | |

## 5. Complete diff and anti-false-green review

| Path/symbol | Change | Behavioral relevance | Risk | Authorized |
|---|---|---|---|---|

- Assertions/tests weakened:
- Skip/xfail/collection changes:
- Hard-coded or report-only green:
- Verifier/parser/receipt/claim weakening:
- Evidence producer changed by Candidate:
- Unrelated or out-of-scope changes:
- Duplicate route/lifecycle/approval authority:
- Security/data/Git/packaging concerns:

### CI/check provenance, if used

- Exact tested immutable SHA:
- Subject role: `CANDIDATE_HEAD | MERGE_GROUP | POST_MERGE_MAIN`
- Check/run identity:
- Expected app/workflow/source:
- Conclusion:
- Actually executed vs skipped/neutral/inherited/stale:
- Supporting only or independently reproduced:

## 6. Exact-base differential and integration subjects

| Verifier/check | Exact base result | Candidate result | Classification | Same environment/signature? | Evidence |
|---|---|---|---|---|---|

Classification: `BASELINE_PASS_CANDIDATE_PASS | CANDIDATE_IMPROVEMENT | EXACT_BASELINE_DEBT | CANDIDATE_REGRESSION | NON_COMPARABLE_BASELINE | INFRASTRUCTURE_OR_POLICY_VARIANCE`

- Baseline debt explicitly allowed by current contract/policy:
- If `EXACT_BASELINE_DEBT`, exact matching failure identity/signature:
- Candidate introduced or worsened any material failure:
- Candidate-specific independent passing evidence:
- Merge-group SHA, if any:
- Merge-group contains newer base or queued changes:
- Post-merge main SHA, if any:
- Integration evidence kept separate from Candidate verdict: `yes`
- Formatting/generated-only commit neutrality physically verified, if claimed:

## 7. Independent verification

| ID | cwd | argv | Result class | Exit | Duration | Changed paths | Evidence |
|---|---|---|---|---:|---:|---|---|

- Reviewer independence: `INDEPENDENT_REVIEWER | PARTIAL_INDEPENDENCE | UNVERIFIED`
- Verification sandbox/worktree identity:
- Toolchain/interpreter/build-tool versions:
- Network policy/dependency:
- Writable temporary/output scope:
- Canonical repository/task state unchanged after verification:
- Baseline/infrastructure/transport/environment/Candidate/evidence/semantic classification:

### Oracle provenance

| Claim/witness | Provenance | Candidate/implementer modified it? | Independence impact | Evidence |
|---|---|---|---|---|

Provenance class: `CONTRACT_DEFINED | PRE_EXISTING | INDEPENDENTLY_AUTHORED | CANDIDATE_AUTHORED | UNKNOWN`

If all decisive oracles are Candidate-authored, do not claim full independent behavior without separate evidence.

### Paired replay for reproducible bug fixes

- Exact base witness command/result:
- Exact Candidate witness command/result:
- Same witness and material environment:
- Expected fail -> pass discrimination proven:
- If not run, why not applicable/available:

## 8. Provenance and attestation

- Applicability: `REQUIRED | SUPPLIED_OPTIONAL | NOT_REQUIRED`
- Physical artifact digest matched:
- Signature/envelope/trusted-root result:
- Statement and predicate type:
- Verifier/signer/builder/repository/workflow policy:
- Verification policy identity/digest, if applicable:
- Source revision/material/input-attestation binding:
- Classification: `VERIFIED | ATTESTATION_INVALID | ATTESTATION_POLICY_MISMATCH | PROVENANCE_ONLY | REQUIRED_ATTESTATION_MISSING | ATTESTATION_NOT_REQUIRED`
- Limitation: provenance does not prove semantic correctness.

## 9. Candidate verdict

- Verdict: `ACCEPT_CANDIDATE | REJECT_CANDIDATE | ACCEPTANCE_BLOCKED | OWNER_DECISION_REQUIRED`
- Evidence basis:
- Candidate blockers:
- Residual debt:
- Base-relative acceptance limitation, if target advanced:
- Maximum supportable claim:
- Prohibited claims:

## 10. Approval readiness

- Status: `READY_FOR_OWNER_APPROVAL | BLOCKED_BY_TRANSPORT_FRESHNESS | BLOCKED_BY_HOST_BINDING | BLOCKED_BY_LIFECYCLE_STATE | NOT_EVALUATED`
- Task still pending acceptance:
- Exact Candidate binding current:
- Approval action host-bound:
- Approval object created: `false`
- Candidate already approved/integrated:
- Required live fields to reacquire:
- Approval-gate blockers:
- Latest-target/integration context must still be reacquired: `yes`

## 11. Next gate and prohibited actions

- One next gate:
- Do not execute yet:
