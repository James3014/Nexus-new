# Research Foundations for Candidate Acceptance

Use these sources as design inputs, never as Nexus authority. Repository policy, the exact approved contract, durable task state, and current Nexus transport remain controlling.

## Contents

1. Git immutable subjects
2. Candidate acceptance versus latest-target integration
3. Verification isolation and environment identity
4. CI/check provenance is not equivalent to independent behavior
5. Oracle provenance and patch overfitting
6. in-toto Attestation Framework v1.2
7. SLSA Verification Summary Attestation
8. GitHub artifact attestations and Sigstore
9. GitHub merge queue uses a different integration subject
10. GitHub green status can include non-executed checks
11. Exact-base differential classification and patch overfitting
12. Nexus historical regression lessons


## 1. Git immutable subjects

Git object identifiers name immutable content-addressed objects. Current Git supports SHA-1 object IDs represented by 40 hexadecimal digits and SHA-256 object IDs represented by 64 hexadecimal digits. `git cat-file` can resolve an object and report its type, size, and content.

Adaptation:

- Accept only full 40- or 64-hex Git OIDs for immutable Candidate/base/tree subjects.
- Reject 41-63-character pseudo-OIDs and abbreviated names as acceptance subjects.
- Resolve the physical object and object type when available.
- Keep refs such as branches/tags separate from the immutable Candidate subject.
- Verify ancestry from the exact expected base rather than trusting branch labels.

Primary sources:

- https://git-scm.com/docs/hash-function-transition.html
- https://git-scm.com/docs/git-cat-file.html

## 2. Candidate acceptance versus latest-target integration

GitHub merge queue validates a pull request after combining it with the latest target branch and, where applicable, changes ahead of it in the queue. This is a different time and subject from reviewing the original immutable Candidate against its expected base.

Adaptation:

- Treat target-branch advancement after an otherwise stable Candidate audit as an integration-context change, not automatically a Candidate defect.
- State Candidate acceptance as base-relative.
- Never silently retarget/rebase/rewrite the Candidate during acceptance.
- Require a later owner/integration gate to reacquire latest canonical target state and revalidate merge/integration conditions.

Primary sources:

- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/merging-a-pull-request-with-a-merge-queue
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches

## 3. Verification isolation and environment identity

Bazel hermeticity and sandboxing isolate actions from undeclared host state and constrain visible inputs/outputs. Reproducible Builds treats toolchain and environment identity as material to independent reproduction.

Adaptation:

- Use a disposable, non-canonical verification sandbox/worktree rather than requiring a literally read-only filesystem.
- Permit temporary/build writes only inside the disposable verification scope.
- Record material toolchain/interpreter/build-tool versions and network dependence.
- Confirm the canonical repository and durable task state are unchanged after verification.
- Treat uncontrolled host-state dependence as evidence debt, not as a silent pass.

Primary sources:

- https://bazel.build/docs/sandboxing
- https://bazel.build/basics/hermeticity
- https://reproducible-builds.org/docs/perimeter/
- https://reproducible-builds.org/docs/recording/

## 4. CI/check provenance is not equivalent to independent behavior

GitHub distinguishes check runs and commit statuses. A conditionally skipped job can report `Success`, and protected-branch policy may require a check from a specific GitHub App. Required checks are evaluated against a particular head/test-merge subject.

Adaptation:

- Bind material CI evidence to the exact Candidate SHA or exact merge subject it actually tested.
- Record check/run identity and expected app/workflow when policy requires it.
- Distinguish executed success from skipped, neutral, inherited, stale, or unexpected-source status.
- Do not count a green label as independent behavior unless the intended verification actually executed.
- Treat CI as supporting evidence; independently reproduce behavior when the contract requires independent acceptance.

Primary sources:

- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks
- https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches

## 5. Oracle provenance and patch overfitting

Program-repair research has long shown that a patch can pass an available test suite while remaining semantically incorrect. Recent empirical studies of coding-agent tests also show that agent-generated tests have distinct quality risks, including elevated mocking and environmental/flakiness concerns.

Adaptation:

- Separate reviewer independence from oracle independence.
- Classify decisive behavioral evidence by provenance: contract-defined, pre-existing, independently authored, Candidate-authored, or unknown.
- Do not treat Candidate/implementer-authored tests as an independent oracle merely because another reviewer ran them.
- If all decisive behavioral evidence is Candidate-authored, cap the result at `PARTIAL_INDEPENDENCE` and route deep test-quality evaluation to `nexus-test-quality-audit`.
- For reproducible bug fixes, prefer the same witness failing on the exact expected base and passing on the exact Candidate.

Research sources:

- Yingfei Xiong et al., *Identifying Patch Correctness in Test-Based Program Repair*, arXiv:1706.09120.
- Zhongxing Yu et al., *Alleviating Patch Overfitting with Automatic Test Generation*, arXiv:1810.10614.
- Andre Hora and Romain Robbes, *Are Coding Agents Generating Over-Mocked Tests? An Empirical Study*, arXiv:2602.00409.
- Preet Jhanglani et al., *Beyond Test Presence: Assessing the Quality and Robustness of Agent-Generated Tests in Open-Source Projects*, arXiv:2607.12068.

The coding-agent papers are empirical risk indicators, not Nexus policy and not proof that a particular agent-authored test is bad.

## 6. in-toto Attestation Framework v1.2

The in-toto framework separates predicate, statement, envelope, and bundle. A Statement binds authenticated metadata to immutable subjects using digests and identifies the predicate type. Version 1.2 also includes a Simple Verification Result predicate family.

Adaptation:

- Match attestation subjects by immutable digest, not filename, branch, tag, or prose label.
- Verify statement/predicate semantics and policy expectations, not only envelope/signature validity.
- Keep authentication of a claim separate from correctness of the Candidate.
- Do not turn Candidate acceptance into an attestation signer or policy authority.

Primary sources:

- https://github.com/in-toto/attestation/blob/main/spec/README.md
- https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md
- https://github.com/in-toto/attestation/releases/tag/v1.2.0

## 7. SLSA Verification Summary Attestation

SLSA v1.2 VSA describes a verifier evaluating artifact subjects and a bundle of attestations against a policy. The subject and policy identity remain distinct inputs to the verification claim.

Adaptation:

- Bind the exact artifact/Candidate subject to the verification result.
- Record verifier identity and policy identity/digest when supplied or required.
- Keep VSA/provenance evidence separate from behavioral verification.
- Never infer source correctness, runtime safety, or production readiness solely from a valid VSA.

Primary sources:

- https://slsa.dev/spec/v1.2/verification_summary
- https://slsa.dev/spec/v1.2/verifying-artifacts
- https://slsa.dev/spec/v1.2/attestation-model

## 8. GitHub artifact attestations and Sigstore

GitHub artifact attestations and Sigstore/Cosign provide cryptographic provenance/signature verification tied to artifact identities and identity policy. Authentication does not by itself prove semantic correctness.

Adaptation:

- Verify the physical subject digest before accepting attestation claims.
- Enforce expected signer/builder/repository/workflow identity where the contract requires it.
- Do not install or invoke new signing/verifier tooling through this Skill unless separately authorized.
- Apply artifact provenance only when the contract covers produced artifacts or requires it.

Primary sources:

- https://docs.github.com/en/actions/concepts/security/artifact-attestations
- https://cli.github.com/manual/gh_attestation_verify
- https://docs.sigstore.dev/cosign/verifying/verify/
- https://docs.sigstore.dev/cosign/verifying/attestation/

## Nexus adaptation summary

Apply a three-boundary model:

1. **Executor evidence binding** — bind contract/task/attempt, packet/manifest/receipt, runtime Workforce Admission when applicable, and immutable Candidate identity.
2. **Independent Candidate acceptance** — reproduce behavior in a disposable verification environment with sufficiently independent reviewer and oracle; verify provenance only when applicable.
3. **Owner/integration revalidation** — reacquire current lifecycle/transport and latest target context before approval/integration. Candidate acceptance never substitutes for this later gate.

Do not collapse any of these boundaries.

## Source inventory

Retrieved/reviewed through 2026-08-21. External sources are reference material only and do not define Nexus authority or current repository truth.


## 9. GitHub merge queue uses a different integration subject

GitHub merge queue creates a temporary `merge_group` containing the pull request changes, the latest target branch, and where applicable queued changes ahead of it. The temporary merge-group branch has a different SHA from the original pull-request head and runs its own required checks.

Adaptation:

- bind Candidate acceptance to the immutable Candidate head;
- record merge-group checks under a separate `MERGE_GROUP` subject;
- treat a successful merge-group as integration-context evidence, not retroactive Candidate acceptance evidence;
- reacquire latest-target/integration context before owner integration or post-merge claims.

Primary source:

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue

## 10. GitHub green status can include non-executed checks

GitHub documents that a skipped job can report `Success`, and `neutral`/`skipped` conclusions may be treated as success by dependent GitHub Actions checks. A green UI state therefore does not prove that the intended verifier executed.

Adaptation:

- inspect check/run identity, immutable tested subject, conclusion, expected app/workflow, and whether execution actually occurred;
- keep skipped, neutral, stale, inherited, or unexpected-source results below independent-behavior proof;
- never use a green label alone to override physical verifier evidence.

Primary source:

- https://docs.github.com/en/pull-requests/reference/status-checks

## 11. Exact-base differential classification and patch overfitting

Program-repair research shows that a patch may pass the available test suite while still being semantically wrong, and that strengthening or varying tests can expose overfitting. It also supports comparing behavior before and after a patch rather than treating a single post-patch result as sufficient correctness evidence.

Adaptation:

- use exact-base versus Candidate comparison to attribute failures, not to manufacture a pass;
- call the same material failure on both subjects `EXACT_BASELINE_DEBT` only when the verifier environment and failure signature are genuinely comparable;
- classify base-pass/Candidate-fail as `CANDIDATE_REGRESSION`;
- keep semantic/oracle correctness separate from baseline attribution.

Research sources:

- Yingfei Xiong et al., *Identifying Patch Correctness in Test-Based Program Repair*, arXiv:1706.09120.
- Zhongxing Yu et al., *Test Case Generation for Program Repair: A Study of Feasibility and Effectiveness*, arXiv:1703.00198.
- Zhongxing Yu et al., *Alleviating Patch Overfitting with Automatic Test Generation*, arXiv:1810.10614.

## 12. Nexus historical regression lessons

See `references/nexus-regression-lessons.md` for bounded historical examples that motivated exact-base debt attribution, Candidate/merge subject separation, and semantically-neutral follow-up verification. These examples are regression design inputs only; they are not current repository truth.
