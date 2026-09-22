<!-- Detailed procedure, reconciled from the supplied original. Relative paths remain skill-root-relative. -->

# Nexus Candidate Acceptance Audit

Audit one exact Candidate at `OBSERVE` and `VERIFY`. Produce an independent recommendation. Never create approval or integration authority.

Read:

- `references/chatgpt-nexus-mcp-operating-contract.md` before using Nexus MCP;
- `references/research-foundations.md` before evaluating Git identity, CI evidence, verification isolation, oracle provenance, or attestations;
- `references/acceptance-template.md` for the human report;
- `references/acceptance-result-schema.md` for `nexus.candidate_acceptance.v3`;
- `references/nexus-skill-chain-contract.md` before binding executor evidence or handing evidence downstream.

## Authority boundary

- Distrust implementer PASS, summary, commit title, receipt, CI green, signature, VSA, or attestation until independently bound to the exact Candidate and policy.
- Do not edit, write, stage, commit, merge, push, delete, dispose, retry, resume, clean up, repair, sign, attest, approve, or integrate.
- Do not call `nexus_candidate_approve`, `nexus_candidate_integrate`, `nexus_candidate_bind_integration`, `nexus_candidate_dispose`, `nexus_task_finish`, or another lifecycle mutation action.
- Do not use `nexus_task_run` or another mutation-capable execution action as a substitute for a safe verification surface.
- Do not weaken tests, verifiers, parsers, receipt requirements, provenance policy, or claim boundaries.
- Do not deep-grade test suites here. Route assertion-depth, mutation-resistance, tamper-control, or comprehensive REQ/AC coverage questions to `nexus-test-quality-audit`.
- Treat acceptance as Candidate-relative evidence only. Do not infer latest-target integration safety, release readiness, deployment readiness, production readiness, or public-claim authority.
- Do not turn an identical base/Candidate failure into a synthetic PASS. Classify baseline debt separately and require explicit contract/policy allowance before it can coexist with Candidate acceptance.
- Do not use a merge-queue `merge_group` SHA or post-merge main SHA as though it were the original Candidate subject. Record each immutable subject and the claim it actually supports.
- Treat this Skill as ChatGPT-side evidence review, not a Nexus Verifier, approval service, signing authority, policy engine, merge queue, or promotion gate.

## Trigger gate

Use this Skill only when all of the following are true or can be resolved:

- one exact Candidate is named by task and immutable Candidate identity;
- the user asks whether that Candidate is acceptable before owner approval;
- implementation is complete enough to review;
- the work is not merely a `DIRECT_CANONICAL` receipt without a Candidate.

Route elsewhere:

- general branch, HEAD, wiring, runtime, or completion truth -> `nexus-current-state-audit`;
- MCP OAuth, schema, root, permission, or host-binding design -> `nexus-mcp-access-audit`;
- REQ/AC test depth, assertion quality, mutation resistance, or verifier-grade analysis -> `nexus-test-quality-audit`;
- implementation or repair -> `nexus-mcp-task-executor` or `nexus-bug-diagnosis`;
- merge-conflict resolution -> `nexus-merge-conflict-resolution`.

If no immutable Candidate exists, do not reinterpret a completion report as Candidate acceptance.

## Required input

Resolve or mark blocked:

- contract kind: `TRACKED_TASK_CARD` or `OWNER_INLINE`;
- campaign/task ID, current task status, implementer attempt, reviewer attempt;
- Task Card path/hash, or exact Owner-inline `contract_hash` and expiry;
- expected base, Candidate commit, tree, state hash, physical diff hash, and verified-receipt hash;
- current executor receipt and any compiled packet/execution manifest lineage that exists;
- for model-specific `COMPILED_PACKET` execution, execution-time Workforce Admission side evidence when exact worker/model identity is material;
- repository root, start/end HEAD, branch, dirty state, and integration state;
- exact allowed paths, mandatory commands, evidence mode, and claim ceiling;
- Gateway server instance, canonical root, action/manifest/schema/policy/lifecycle hashes, reload/review flags, and host action-binding state;
- verification-environment identity, toolchain versions, network policy, writable temporary/output scope, and canonical-repository final state;
- oracle provenance for material behavioral claims: contract-defined, pre-existing, independently authored, Candidate-authored, or unknown;
- CI/check provenance when used: exact immutable tested subject, subject role (`CANDIDATE_HEAD`, `MERGE_GROUP`, or `POST_MERGE_MAIN`), check/run identity, conclusion, actual execution versus skip/neutral, and expected app/workflow when policy requires it;
- exact expected-base verifier result when baseline debt, regression attribution, or paired replay is material; use the same verifier and materially equivalent environment when comparison is claimed;
- immutable artifact and attestation subjects when the contract covers produced artifacts.

Use only full Git object IDs as immutable commit/tree subjects: exactly 40 hexadecimal characters for SHA-1 repositories or 64 for SHA-256 repositories. Never use a mutable branch, tag, filename, container tag, abbreviated OID, or chat assertion as the Candidate subject.

## Evidence axes

Keep six axes independent:

1. **Authority** — prove that the exact contract authorized this task, attempt, paths, Candidate production, and material model-specific execution binding.
2. **Subject identity** — physically match commit, tree, state, diff, receipt, evidence, and artifact digests.
3. **Lineage** — prove ancestry from the expected base without rewrite, contamination, or subject substitution.
4. **Independent behavior** — reproduce required behavior with a sufficiently independent reviewer, environment, and oracle.
5. **Provenance** — when required or supplied, verify authenticated statements against exact subject, verifier/builder, policy, source, workflow, and material identities.
6. **Claim discipline** — keep the verdict within evidence mode, reviewer/oracle independence, current state, and authority.

Never collapse these axes into a trust score. A valid signature does not prove behavior. A green CI label does not prove that the intended check executed. Passing Candidate-authored tests alone does not prove an independent oracle. An identical base/Candidate failure is not a pass. Candidate acceptance does not prove latest-target integration safety.

## Workflow

### 1. Freeze the acceptance and transport clocks

Capture at audit start and end:

- repository root, branch, HEAD, dirty state, task status, Candidate identity, and expected base;
- server instance, canonical root, action contract/definition, tool manifest, full schema, lifecycle revision, and permission policy;
- runtime-source, reload, action-review, and permission-review state;
- approved/frozen action snapshot, host-bound invocation surface, and live server manifest when available.

Keep these cases separate:

- Gateway-start repository drift before the audit is informational;
- immutable Candidate/task/root/server/schema/policy drift during the audit may stale or block the audit;
- target/base branch advancement that does not change the frozen Candidate is an **integration-context change**, not automatically a Candidate defect;
- runtime-source drift or reload/review flags block reliance on affected loaded actions;
- discovery followed by direct-recipient `Resource not found` is `HOST_ACTION_BINDING_GAP` unless server rejection is proven.

Do not silently retarget an accepted Candidate to a newer canonical head. Require the eventual owner/integration gate to reacquire latest-target state and revalidate there.

### 2. Bind current executor and contract lineage

For `TRACKED_TASK_CARD`, require the physical Task Card path/hash and current task/attempt binding.

For `OWNER_INLINE`, require the exact bounded contract hash, owner confirmation evidence, expiry, allowed files, verifier commands, task/attempt identity, and Candidate authority. If executor or lifecycle evidence cannot physically bind the Owner-inline contract, return `ACCEPTANCE_BLOCKED`.

For current executor lineage, prefer and validate:

- `nexus.compiled_model_task_packet.v3` when a compiled packet exists;
- `nexus.chatgpt_mcp_execution.v4`;
- `nexus.mcp_execution_receipt.v2`.

Treat executor v3-manifest/v1-receipt lineage only as historical compatibility evidence and report the weaker claim. Never relabel old artifacts as current.

For a `COMPILED_PACKET` Candidate with material worker/model binding, require physical execution-time Workforce Admission side evidence and validate it against the physical packet. Compile-time admission is not a standing dispatch lease. Missing or mismatched runtime admission blocks or fails the authority axis; it cannot support `ACCEPT_CANDIDATE`.

Do not convert chat context into Owner-inline authority. Do not require a Task Card when a valid Owner-inline Candidate contract is physically proven.

### 3. Freeze the immutable subject set

Record:

- source subject: repository + expected base + Candidate commit + tree + state + diff;
- contract subject: task + attempt + Task Card hash or Owner-inline `contract_hash`;
- execution subjects: packet, manifest, executor receipt, runtime Workforce Admission when applicable, command evidence, verified receipt, and durable task-state evidence;
- artifact subjects: SHA-256, OCI digest, or other policy-approved immutable digest for every produced artifact covered by the contract;
- attestation subjects when supplied or required.

Resolve full Git objects physically where available; verify object type and ancestry rather than trusting ref names.

Classify mismatches as:

- `CANDIDATE_IDENTITY_MISMATCH`
- `LINEAGE_UNVERIFIED`
- `ARTIFACT_SUBJECT_MISMATCH`
- `EVIDENCE_BINDING_MISMATCH`
- `CONTRACT_BINDING_MISMATCH`
- `ATTEMPT_BINDING_MISMATCH`
- `WORKFORCE_BINDING_MISMATCH`

### 4. Verify lifecycle state without mutation

Read the exact durable task before and after review when available. Confirm:

- the same task and implementer attempt remain bound;
- the Candidate is still pending acceptance;
- exact commit/tree/state/verified-receipt binding matches;
- the Candidate has not already been approved, integrated, superseded, rejected, or disposed;
- pending owner actions are not acceptance evidence.

If task status cannot be read because the host cannot bind a discovered action, record the host-binding gap. Do not invoke retry, resume, reconcile, finish, approve, bind-integration, integrate, or dispose to discover state.

### 5. Review the complete physical diff and evidence production path

Inspect production, test, config, generated, dependency, documentation, deletion, permission, schema, packaging, and verifier changes. Verify:

- allowed paths and file-count limits;
- no unrelated changes or scope laundering;
- no second route, verifier, receipt, lifecycle, approval, or integration authority;
- no weakened assertion, skip/xfail, collection, parser, verifier, or claim gate;
- no hard-coded green result, fake receipt, secret leakage, unsafe command construction, artifact substitution, or evidence producer modified to bless its own output.

If CI/check evidence is material, bind it to the exact immutable subject it actually tested. Record the subject role as `CANDIDATE_HEAD`, `MERGE_GROUP`, or `POST_MERGE_MAIN`. Distinguish executed success from `skipped`, `neutral`, inherited, stale, or unexpected-app status. Treat CI green as supporting evidence, not independent behavior by itself.

If a commit is claimed to be formatting-only, generated-only, or semantically neutral, verify that claim physically. A commit title, implementer statement, or whitespace-looking diff is not enough; use bounded diff normalization, AST/semantic comparison where practical, and the relevant verifier set.

A clean diff shape is necessary but not sufficient.

### 6. Classify exact-base verification delta

When any material verifier/check fails, or when the Candidate is being accepted despite known baseline debt, compare the exact expected base and exact Candidate using the same command and materially equivalent environment whenever safe and available.

Classify each material verifier outcome as exactly one of:

- `BASELINE_PASS_CANDIDATE_PASS` — both subjects pass;
- `CANDIDATE_IMPROVEMENT` — base fails and Candidate passes;
- `EXACT_BASELINE_DEBT` — base and Candidate fail with the same material failure signature and the Candidate does not worsen the condition;
- `CANDIDATE_REGRESSION` — base passes but Candidate fails, or the Candidate adds/worsens a material failure;
- `NON_COMPARABLE_BASELINE` — command, environment, source, policy, or dependency differences prevent a valid comparison;
- `INFRASTRUCTURE_OR_POLICY_VARIANCE` — the observed difference is attributable to infrastructure/policy execution rather than Candidate behavior.

For `EXACT_BASELINE_DEBT` require more than equal failure counts. Compare failing test/check identity, failure class/message or semantic witness, exit/result classification, and the affected contract surface. If equivalence cannot be established, use `NON_COMPARABLE_BASELINE`.

`EXACT_BASELINE_DEBT` means **not introduced by this Candidate**. It does not mean the verifier passed. It may coexist with `ACCEPT_CANDIDATE` only when current contract/policy explicitly permits that debt and all Candidate-specific required behavior has sufficient independent evidence. Otherwise return `ACCEPTANCE_BLOCKED` or `OWNER_DECISION_REQUIRED`.

A material `CANDIDATE_REGRESSION` fails the independent-behavior axis and normally requires `REJECT_CANDIDATE`.

Record merge-queue or post-merge results separately. A `merge_group` SHA tests an integration subject that may contain a newer base and other queued changes. A post-merge main SHA is yet another subject. Neither retroactively repairs missing Candidate contract, executor, oracle, or identity evidence.

### 7. Reproduce required behavior independently

Run only exact allowlisted verification in a disposable, non-canonical verification environment. Permit temporary/build writes only inside the isolated verification scope. Do not mutate the canonical checkout, durable task lifecycle, approval state, or Candidate subject.

Record:

- reviewer identity/attempt and independence class;
- sandbox/worktree identity and starting Candidate object;
- argv, cwd, result class, exit code, duration, changed paths, and evidence reference;
- toolchain/interpreter/build-tool versions and material environment inputs;
- network state or explicit network dependency;
- final sandbox state and proof that canonical repository/task state stayed unchanged.

Assess oracle provenance separately from reviewer identity. If all decisive assertions or witnesses were authored or modified by the Candidate/implementer and no contract-defined, pre-existing, or independently authored oracle exists, classify independent behavior as at most `PARTIAL_INDEPENDENCE` and block `ACCEPT_CANDIDATE` until an independent oracle exists or `nexus-test-quality-audit` provides sufficient evidence.

For bug fixes with a stable reproducer, prefer paired replay:

1. run the same bounded witness against the exact expected base and observe the expected failure;
2. run the same witness against the exact Candidate and observe the expected pass;
3. record any environment difference and do not interpret unrelated baseline failures as Candidate failure.

Do not require paired replay when the contract is not a bug-fix/reproducible-defect task or the base witness is unsafe/unavailable; record the limitation instead.

Separate:

- pre-existing baseline failure;
- infrastructure/provider/host-binding/transport failure;
- verification-environment contamination;
- Candidate regression;
- invalid, nondiscriminating, or Candidate-only oracle;
- evidence mismatch;
- semantic behavior failure.

Reviewer attempt inequality alone is insufficient. Classify independence as `INDEPENDENT_REVIEWER`, `PARTIAL_INDEPENDENCE`, or `UNVERIFIED`. `ACCEPT_CANDIDATE` requires `INDEPENDENT_REVIEWER` and a materially independent oracle.

### 8. Verify provenance only when applicable

Verify signatures/trusted roots, statement/envelope, subject digest, predicate type, verifier/signer/builder identity, repository/workflow/event policy, source revision, material/input attestations, policy identity/digest when supplied, and every physical artifact digest.

Use:

- `ATTESTATION_INVALID`
- `ATTESTATION_POLICY_MISMATCH`
- `PROVENANCE_ONLY`
- `ATTESTATION_NOT_REQUIRED`
- `REQUIRED_ATTESTATION_MISSING`

Do not require attestation for a source-only Candidate unless the contract requires it. Do not infer semantic correctness from provenance, VSA, signature, or transparency evidence alone.

### 9. Determine Candidate verdict and approval readiness separately

Use one Candidate verdict:

- `ACCEPT_CANDIDATE`
- `REJECT_CANDIDATE`
- `ACCEPTANCE_BLOCKED`
- `OWNER_DECISION_REQUIRED`

Then classify the separate owner-approval gate:

- `READY_FOR_OWNER_APPROVAL`
- `BLOCKED_BY_TRANSPORT_FRESHNESS`
- `BLOCKED_BY_HOST_BINDING`
- `BLOCKED_BY_LIFECYCLE_STATE`
- `NOT_EVALUATED`

Allow a structurally valid negative result to contain physical mismatches only when the corresponding evidence axis explicitly records `FAIL` or `BLOCKED`. Never allow the same mismatch inside `ACCEPT_CANDIDATE`.

Allow `ACCEPT_CANDIDATE` to coexist with a blocked approval gate. Never construct or mint the expiring approval object. Record the fields the owner approval action must reacquire: task, attempt, contract, Task Card when applicable, lifecycle revision, server instance, tool manifest, full schema, permission policy, Candidate commit/tree/state, and verified-receipt hash.

If the canonical target advanced after the frozen Candidate/base audit, state that acceptance is base-relative and require latest-target/integration revalidation later. Do not reject the immutable Candidate solely because the target moved. If merge-group or post-merge evidence exists, preserve it as integration-context evidence tied to its own SHA; do not use it to rewrite the Candidate verdict subject.

### 10. Validate and stop

Create `acceptance-result.json` using `nexus.candidate_acceptance.v3` and validate it:

```bash
python -B scripts/validate_acceptance_result.py acceptance-result.json \
  --task-card TASK-CARD.md \
  --compiled-packet packet.json \
  --execution-manifest execution-manifest.json \
  --executor-receipt execution-receipt.json \
  --runtime-admission runtime-workforce-admission.json \
  --report acceptance.validation.json
```

Pass `--runtime-admission` only when applicable. For current model-specific `COMPILED_PACKET` Candidate acceptance, require it. Omit physical arguments that genuinely do not exist and lower the claim accordingly. A structurally valid result is not physical acceptance evidence.

Return the human report using `references/acceptance-template.md`, the validated result when requested, one exact next gate, and prohibited next actions. Do not auto-chain.

## Skill evaluation

Use `evals/evals.json`. Grade contract/attempt binding, current executor lineage, runtime Workforce Admission binding, exact Git identity, lifecycle/transport freshness, exact-base differential classification, verification isolation, oracle independence, paired replay when applicable, CI/check subject binding, merge-subject separation, anti-false-green controls, provenance policy, approval-readiness separation, claim discipline, and refusal to mutate.

## Cross-Skill handoff

Produce `nexus.candidate_acceptance.v3`. Preserve its digest, Candidate subject, expected base, reviewer attempt, evidence cutoff, Candidate verdict, approval readiness, and maximum claim. Preserve model-specific execution-time Workforce Admission as side evidence when it was required for the audit. Require live approval bindings and latest-target/integration context to be reacquired before owner action. Acceptance never grants approval, integration, push, cleanup, release, or public-claim authority.
